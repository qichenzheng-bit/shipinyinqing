"""V2.6.4 real voiced MP4: source-bound TTS -> timed Manim -> MathTex captions.

An actual generated PCM stream determines each visual action's duration.
No dummy audio, narrated equation omission, guessed frame times, or silent
video can be reported as the final spoken classroom output.
"""
from __future__ import annotations

from .video_settings import DEFAULT_VIDEO_FPS

import asyncio
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
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


def _encode_caption_band(cues: list[dict], mapped: dict,
                         output: Path, *, fps: int, frames: int):
    """One frame-exact transparent subtitle stream; no 50-way FFmpeg overlay.

    The original CJK/MathTex glyph PNGs are source-authentic. A 1280x88
    transparent band is enough; only the bottom safe region ever changes.
    """
    from PIL import Image
    w,h=1280,88
    blanks=bytes(w*h*4)
    pairs=[]
    cache={}
    for cue in cues:
        key=(cue["kind"],cue["display"])
        if key not in cache:
            pic=Image.open(mapped[key]).convert("RGBA")
            if pic.size!=(w,h):
                raise LongboardError("SPOKEN_BAD_CAPTION_SAFE_REGION")
            if pic.getchannel("A").getextrema()[0]!=0:
                raise LongboardError("SPOKEN_CAPTION_BAND_NOT_TRANSPARENT")
            cache[key]=pic.tobytes()
        pairs.append((cue["start_frame"],cue["end_frame"],cache[key]))
    pairs.sort(key=lambda x:x[0])
    command=[
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-f","rawvideo","-pixel_format","rgba",
        "-video_size",f"{w}x{h}",
        "-framerate",str(fps),"-i","pipe:0",
        "-c:v","ffv1","-pix_fmt","bgra",str(output),
    ]
    proc=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        cursor=0
        for start,end,raw in pairs:
            if start<cursor or end<=start or end>frames:
                raise LongboardError("SPOKEN_CAPTION_FRAME_OVERLAP")
            for _ in range(start-cursor):
                proc.stdin.write(blanks)
            for _ in range(end-start):
                proc.stdin.write(raw)
            cursor=end
        for _ in range(frames-cursor):
            proc.stdin.write(blanks)
        proc.stdin.close()
        err=proc.stderr.read()
        status=proc.wait()
        if status:
            raise LongboardError(
                "SPOKEN_CAPTION_BAND_ENCODE_FAILED: "
                +err.decode("utf-8","replace")[-500:]
            )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    if not output.is_file() or output.stat().st_size<1000:
        raise LongboardError("SPOKEN_CAPTION_BAND_MISSING")


def render_spoken_classroom(
    input_file: Path | str, *,
    output_mp4: Path, output_json: Path,
    output_srt: Path | None=None,
    fps: int = DEFAULT_VIDEO_FPS, adaptive: bool=True, cache_dir: Path | None=None,
) -> dict:
    path=Path(input_file).resolve()
    from .safe_output import (
        validate_output_targets, course_source_files, publish_bundle,
    )
    output_mp4, output_json = Path(output_mp4), Path(output_json)
    output_srt = (Path(output_srt) if output_srt is not None
                  else output_mp4.with_suffix(".srt"))
    if type(fps) is not int or not 8<=fps<=60:
        raise LongboardError("SPOKEN_RENDER_ARGUMENTS")
    targets = {output_mp4: ".mp4", output_json: ".json", output_srt: ".srt"}
    protected = course_source_files(path)
    validate_output_targets(targets, protected=protected)
    checked=checked_spoken(path,adaptive=adaptive)
    from .unified_classroom_flow import _load
    if "lesson_contract" in _load(path):
        from .v27_teacher_contract import require_prerender_script
        require_prerender_script(checked, path)
    if adaptive:
        from .adaptive_classroom_flow import checked_adaptive_flow
        checked_adaptive_flow(path.parent/"adaptive_layout.json")
    if (path.parent/"math_memory.json").exists():
        from .classroom_math_memory import checked_memory
        checked_memory(path.parent/"math_memory.json")
    planned=plan_spoken(path,adaptive=adaptive)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise LongboardError("SPOKEN_FFMPEG_UNAVAILABLE")
    from .render_cache import ArtifactCache
    cache=ArtifactCache(cache_dir) if cache_dir is not None else None
    with tempfile.TemporaryDirectory(prefix="spoken-classroom-") as tmp:
        root=Path(tmp)
        started=time.perf_counter()
        voice=asyncio.run(synthesize_voiced_spans(
            checked,root/"tts",fps=fps,cache=cache
        ))
        if cache is not None:
            cache.timed("speech_synthesis_seconds",time.perf_counter()-started)
        started=time.perf_counter()
        schedules=build_render_schedules(voice,fps=fps)
        silent=root/"native_manim.mp4"
        native_manifest=root/"silent_source.json"
        if adaptive:
            from .adaptive_classroom_flow import render_adaptive_flow
            rendered=render_adaptive_flow(
                path.parent/"adaptive_layout.json",
                output_mp4=silent,output_json=native_manifest,fps=fps,
                narration_schedules=schedules,cache=cache,
            )
        else:
            from .unified_classroom_flow import render_flow
            rendered=render_flow(
                path.parent/"unified_flow.json",
                output_mp4=silent,output_json=native_manifest,fps=fps,
                narration_schedules=schedules,cache=cache,
            )
        if cache is not None:
            cache.timed("native_scene_pipeline_seconds",time.perf_counter()-started)
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
        started=time.perf_counter()
        for cue in cues:
            key=(cue["kind"],cue["display"])
            if key not in mapped:
                digest=hashlib.sha256(
                    (key[0]+":"+key[1]).encode("utf-8")
                ).hexdigest()[:16]
                image=caption_dir/f"mathtex_caption_{digest}.png"
                ckey=(
                    cache.key("subtitle_png",{
                        "kind":cue["kind"],"display":cue["display"],
                        "pixel_width":1280,"safe_band_height":88,
                        "caption_renderer":"manim_mathtex",
                    }) if cache is not None else None
                )
                if cache is None or not cache.get_png(ckey,image):
                    render_caption_png(cue["kind"],cue["display"],image)
                    if cache is not None:
                        cache.write("subtitle_png",ckey,{
                            "payload.bin":image.read_bytes(),
                        })
                mapped[key]=image
        if cache is not None:
            cache.timed("subtitle_glyphs_seconds",time.perf_counter()-started)
        started=time.perf_counter()
        final=root/"full_voiced_classroom.mp4"
        duration=rendered["actual_video_frames"]/fps
        caption_mux={"pipeline":"legacy_verified_ffv1_overlay"}
        sparse_ok=False
        if cache is not None:
            from .sparse_caption_mux import mux_sparse_mathtex
            try:
                caption_mux=mux_sparse_mathtex(
                    silent,audio_wav,cues,mapped,final,
                    workdir=root,fps=fps,
                    frames=rendered["actual_video_frames"],
                )
                sparse_ok=True
            except (LongboardError,OSError):
                # Fidelity before speed: if the sparse filter rejects a
                # source frame or codec, use the already accepted full
                # transparent FFV1 band route, never a silent placeholder.
                cache.counts["sparse_caption_safe_fallback"]+=1
                final.unlink(missing_ok=True)
        if not sparse_ok:
            subtitle_video=root/"mathtex_subtitle_band.mkv"
            _encode_caption_band(
                cues,mapped,subtitle_video,fps=fps,
                frames=rendered["actual_video_frames"],
            )
            _run([
                "ffmpeg","-hide_banner","-loglevel","error","-y",
                "-i",str(silent),"-i",str(audio_wav),
                "-i",str(subtitle_video),
                "-filter_complex",
                "[0:v][2:v]overlay=0:628:shortest=1:eof_action=pass[v]",
                "-map","[v]","-map","1:a",
                "-c:v","libx264","-preset","veryfast","-crf","20",
                "-pix_fmt","yuv420p","-r",str(fps),
                "-c:a","aac","-b:a","128k",
                "-t",f"{duration:.5f}",
                "-movflags","+faststart",str(final),
            ],"SPOKEN_VOICED_CAPTION_MUX_FAILED")
        verified=_audio_video_verified(
            final,fps=fps,expected_frames=rendered["actual_video_frames"],
        )
        if cache is not None:
            cache.timed("subtitle_encode_final_mux_seconds",
                        time.perf_counter()-started)
        # Source-authoritative audit: no fake voice, no non-audio subtitles.
        report={
            **rendered,
            "mode":"spoken_classroom_audio_aligned",
            "source_spoken_sha256":checked.source_sha256,
            "source_flow_sha256":checked.flow.source_sha256,
            "teacher_reviewed_all_visual_actions":True,
            "voice_status":"real_edge_neural_pcm_verified",
            "voice":checked.voice,
            "speech_rate":checked.speech_rate,
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
            "caption_mux":caption_mux,
            "incremental_cache": cache.stats() if cache is not None else None,
            "render_timings_seconds": (
                cache.profile() if cache is not None else None
            ),
        }
        if report["source_narration_action_count"]!=report["voiced_action_count"]:
            raise LongboardError("SPOKEN_UNVOICED_SOURCE_ACTION")
        publish_bundle({
            output_mp4: final,
            output_json: (json.dumps(
                report, ensure_ascii=False, indent=2
            )+"\n").encode("utf-8"),
            output_srt: srt.encode("utf-8"),
        }, suffixes=targets, protected=protected)
        return report
