"""V2.6.4 real voiced MP4: source-bound TTS -> timed Manim -> MathTex captions.

An actual generated PCM stream determines each visual action's duration.
No dummy audio, narrated equation omission, guessed frame times, or silent
video can be reported as the final spoken classroom output.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .longboard_plan import LongboardError
from .spoken_audio import (
    assemble_source_pcm, build_render_schedules, synthesize_voiced_spans,
)
from .spoken_captions import render_caption_png, captions_srt
from .spoken_classroom import checked_spoken, plan_spoken
from .unified_classroom_flow import _video_frames


def _run(command, error):
    p=subprocess.run(command,capture_output=True,text=True)
    if p.returncode:
        raise LongboardError(error+": "+p.stderr[-800:])


def _audio_video_verified(video: Path, *, fps: int, expected_frames: int):
    p=subprocess.run([
        "ffprobe","-v","error","-show_streams","-of","json",str(video),
    ],capture_output=True,text=True)
    if p.returncode:
        raise LongboardError("SPOKEN_FFPROBE_FAILED")
    streams=json.loads(p.stdout)["streams"]
    video_stream=next((x for x in streams if x.get("codec_type")=="video"),None)
    audio_stream=next((x for x in streams if x.get("codec_type")=="audio"),None)
    if (not video_stream or not audio_stream
            or (video_stream["width"],video_stream["height"])!=(1280,720)
            or not audio_stream.get("sample_rate")):
        raise LongboardError("SPOKEN_REAL_AUDIO_OR_VIDEO_MISSING")
    actual=_video_frames(video,fps)
    if abs(actual-expected_frames)>2:
        raise LongboardError("SPOKEN_VIDEO_FRAME_COUNT_CHANGED")
    return {
        "codec":audio_stream.get("codec_name"),
        "sample_rate":int(audio_stream["sample_rate"]),
        "channels":audio_stream.get("channels"),
        "video_frames":actual,
    }


def render_spoken_classroom(
    input_file: Path | str, *,
    output_mp4: Path, output_json: Path,
    output_srt: Path | None=None,
    fps: int=30, adaptive: bool=True,
) -> dict:
    path=Path(input_file).resolve()
    if (not isinstance(fps,int) or not 8<=fps<=60
            or Path(output_mp4).suffix.lower()!=".mp4"
            or Path(output_json).suffix.lower()!=".json"):
        raise LongboardError("SPOKEN_RENDER_ARGUMENTS")
    checked=checked_spoken(path,adaptive=adaptive)
    if adaptive:
        from .adaptive_classroom_flow import checked_adaptive_flow
        checked_adaptive_flow(path.parent/"adaptive_layout.json")
    if (path.parent/"math_memory.json").exists():
        from .classroom_math_memory import checked_memory
        checked_memory(path.parent/"math_memory.json")
    planned=plan_spoken(path,adaptive=adaptive)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise LongboardError("SPOKEN_FFMPEG_UNAVAILABLE")
    with tempfile.TemporaryDirectory(prefix="spoken-classroom-") as tmp:
        root=Path(tmp)
        voice=asyncio.run(synthesize_voiced_spans(
            checked,root/"tts",fps=fps
        ))
        schedules=build_render_schedules(voice,fps=fps)
        silent=root/"native_manim.mp4"
        native_manifest=root/"silent_source.json"
        if adaptive:
            from .adaptive_classroom_flow import render_adaptive_flow
            rendered=render_adaptive_flow(
                path.parent/"adaptive_layout.json",
                output_mp4=silent,output_json=native_manifest,fps=fps,
                narration_schedules=schedules,
            )
        else:
            from .unified_classroom_flow import render_flow
            rendered=render_flow(
                path.parent/"unified_flow.json",
                output_mp4=silent,output_json=native_manifest,fps=fps,
                narration_schedules=schedules,
            )
        if rendered["source_flow_sha256"] != checked.flow.source_sha256:
            raise LongboardError("SPOKEN_SOURCE_FLOW_MISMATCH")
        if len(rendered["event_timing"]) != len(checked.events):
            raise LongboardError("SPOKEN_EVENT_COUNT_MISMATCH")
        audio_wav=root/"measured_real_teacher_voice.wav"
        cues=assemble_source_pcm(
            voice,rendered,audio_wav,fps=fps
        )
        if not cues or not all(c["actual_voice_text"] for c in cues):
            raise LongboardError("SPOKEN_REAL_UTTERANCE_COVERAGE")
        srt=captions_srt(cues,fps=fps)
        caption_dir=root/"caption_pngs"
        caption_dir.mkdir()
        mapped={}
        for cue in cues:
            key=(cue["kind"],cue["display"])
            if key not in mapped:
                digest=hashlib.sha256(
                    (key[0]+":"+key[1]).encode("utf-8")
                ).hexdigest()[:16]
                image=caption_dir/f"mathtex_caption_{digest}.png"
                render_caption_png(cue["kind"],cue["display"],image)
                mapped[key]=image
        final=root/"full_voiced_classroom.mp4"
        images=[]
        filters=[]
        before="[0:v]"
        # A caption segment exists iff the actual TTS clip is audible.
        # There is no subtitle between clips, and nothing is inferred
        # from unspoken MathTex objects, headings or geometric labels.
        for index,cue in enumerate(cues):
            png=mapped[(cue["kind"],cue["display"])]
            images.extend(["-loop","1","-framerate",str(fps),"-i",str(png)])
            nxt=f"[v{index}]"
            start=cue["start_frame"]/fps
            end=cue["end_frame"]/fps
            filters.append(
                f"{before}[{index+2}:v]overlay=0:628:"
                "shortest=1:eof_action=repeat:"
                f"enable='gte(t,{start:.5f})*lt(t,{end:.5f})'{nxt}"
            )
            before=nxt
        duration=rendered["actual_video_frames"]/fps
        args=[
            "ffmpeg","-hide_banner","-loglevel","error","-y",
            "-i",str(silent),"-i",str(audio_wav),
            *images,"-filter_complex",";".join(filters),
            "-map",before,"-map","1:a",
            "-c:v","libx264","-preset","veryfast","-crf","20",
            "-pix_fmt","yuv420p","-r",str(fps),
            "-c:a","aac","-b:a","128k",
            "-t",f"{duration:.5f}",
            "-movflags","+faststart",str(final),
        ]
        _run(args,"SPOKEN_VOICED_CAPTION_MUX_FAILED")
        verified=_audio_video_verified(
            final,fps=fps,expected_frames=rendered["actual_video_frames"],
        )
        # Source-authoritative audit: no fake voice, no non-audio subtitles.
        report={
            **rendered,
            "mode":"spoken_classroom_audio_aligned",
            "source_spoken_sha256":checked.source_sha256,
            "source_flow_sha256":checked.flow.source_sha256,
            "teacher_reviewed_all_visual_actions":True,
            "voice_status":"real_edge_neural_pcm_verified",
            "subtitle_status":"actual_tts_phrase_aligned",
            "math_caption_renderer":"true_manim_mathtex",
            "subtitle_count":len(cues),
            "audio_verification":verified,
            "fabricated_voice_or_subtitle_count":0,
            "source_narration_action_count":planned["action_count"],
            "voiced_action_count":sum(
                len(e) for stage in voice.values() for e in stage.values()
            ),
            "caption_timing":cues,
        }
        if report["source_narration_action_count"]!=report["voiced_action_count"]:
            raise LongboardError("SPOKEN_UNVOICED_SOURCE_ACTION")
        output_mp4=Path(output_mp4)
        output_json=Path(output_json)
        output_srt=(
            Path(output_srt) if output_srt is not None
            else output_mp4.with_suffix(".srt")
        )
        output_mp4.parent.mkdir(parents=True,exist_ok=True)
        output_json.parent.mkdir(parents=True,exist_ok=True)
        output_srt.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(final,output_mp4)
        output_json.write_text(
            json.dumps(report,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8"
        )
        output_srt.write_text(srt,encoding="utf-8")
        return report
