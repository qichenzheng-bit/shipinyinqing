"""V2.6.6 frame-exact sparse MathTex caption compositor.

Previously captions were streamed as ~450 KiB of RGBA per video frame,
then encoded to FFV1 and decoded for a second FFmpeg overlay. This renderer
feeds only authored caption changes as source-approved PNGs, using a 1/fps
image demuxer timebase, and overlays them directly during the FINAL video mux.

Every glyph is the identical Manim/MathTex PNG already source-checked in
spoken_captions. A failed pipeline is never published.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .longboard_plan import LongboardError


def make_sparse_caption_playlist(
    cues: list[dict], mapped: dict[tuple[str,str],Path],
    folder: Path, *, fps: int, frames: int,
) -> Path:
    """Build exact source-PNG timeline; reject any frame overlap/gap loss.

    FFconcat needs explicit 'option framerate FPS' for EACH PNG; otherwise
    it assumes image2's 25 fps and can keep a caption for an extra frame.
    Durations are integer frame counts divided by fps.
    """
    from PIL import Image
    if type(fps) is not int or not 8<=fps<=60 or type(frames) is not int or frames<1:
        raise LongboardError("SPARSE_CAPTION_INVALID_VIDEO_CLOCK")
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    blank=folder/"blank.png"
    Image.new("RGBA",(1280,88),(0,0,0,0)).save(blank)
    assets:dict[tuple[str,str],str]={}
    ordered=sorted(cues,key=lambda row:row["start_frame"])
    segments=[]
    cursor=0
    for cue in ordered:
        start,end=cue["start_frame"],cue["end_frame"]
        if (type(start) is not int or type(end) is not int or
                start<cursor or end<=start or end>frames):
            raise LongboardError("SPARSE_CAPTION_FRAME_OVERLAP")
        key=(cue["kind"],cue["display"])
        if key not in mapped:
            raise LongboardError("SPARSE_CAPTION_UNRENDERED_MATHTEX")
        if key not in assets:
            source=Path(mapped[key])
            with Image.open(source) as picture:
                picture.load()
                if (picture.mode!="RGBA" or picture.size!=(1280,88) or
                        picture.getchannel("A").getextrema()[0]!=0):
                    raise LongboardError("SPARSE_CAPTION_INVALID_SAFE_BAND")
            fname=f"caption_{len(assets):04d}.png"
            shutil.copyfile(source,folder/fname)
            assets[key]=fname
        if start>cursor:
            segments.append(("blank.png",start-cursor))
        segments.append((assets[key],end-start))
        cursor=end
    if cursor<frames:
        segments.append(("blank.png",frames-cursor))
    if not segments or sum(n for _,n in segments)!=frames:
        raise LongboardError("SPARSE_CAPTION_FRAME_COVERAGE")
    # A final repeated image marks the final duration in FFconcat.
    parts=["ffconcat version 1.0"]
    for fname,count in segments:
        parts+= [
            f"file '{fname}'",
            f"option framerate {fps}",
            f"duration {count/fps:.12f}",
        ]
    parts+= [f"file '{segments[-1][0]}'",f"option framerate {fps}"]
    listfile=folder/"caption_timeline.ffconcat"
    listfile.write_text("\n".join(parts)+"\n",encoding="utf-8")
    (folder/"source_caption_audit.json").write_text(
        json.dumps({
            "source":"verified_mathtex_png_events",
            "pixel_width":1280,"safe_height":88,
            "fps":fps,"frames":frames,
            "segments":len(segments),
            "unique_glyphs":len(assets),
            "frame_coverage":sum(n for _,n in segments),
        },ensure_ascii=False,indent=2)+"\n",
        encoding="utf-8",
    )
    return listfile


def mux_sparse_mathtex(
    silent_video: Path, audio_wav: Path, cues: list[dict],
    mapped: dict[tuple[str,str],Path], output: Path,
    *, workdir: Path, fps: int, frames: int,
) -> dict:
    """Final H264+AAC export with one render pass, no FFV1 subtitle band."""
    timeline=make_sparse_caption_playlist(
        cues,mapped,Path(workdir)/"sparse_caption_source",
        fps=fps,frames=frames,
    )
    command=[
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-i",str(silent_video),"-i",str(audio_wav),
        "-f","concat","-safe","0","-i",str(timeline),
        "-filter_complex",
        f"[2:v]fps={fps},format=rgba[cap];"
        "[0:v][cap]overlay=0:628:shortest=1:eof_action=pass[v]",
        "-map","[v]","-map","1:a",
        "-frames:v",str(frames),
        "-c:v","libx264","-preset","veryfast","-crf","20",
        "-pix_fmt","yuv420p","-r",str(fps),
        "-c:a","aac","-b:a","128k",
        "-t",f"{frames/fps:.7f}",
        "-movflags","+faststart",str(output),
    ]
    proc=subprocess.run(command,capture_output=True,text=True)
    if proc.returncode or not Path(output).is_file():
        raise LongboardError(
            "SPARSE_CAPTION_DIRECT_MUX_FAILED:"+(proc.stderr or "")[-700:]
        )
    from .unified_classroom_flow import _video_frames
    actual=_video_frames(Path(output),fps)
    if abs(actual-frames)>2:
        raise LongboardError("SPARSE_CAPTION_FINAL_FRAME_MISMATCH")
    return {
        "pipeline":"frame_exact_sparse_png_final_overlay",
        "caption_input":"genuine_manim_mathtex_png",
        "subtitle_frames":frames,
        "output_frames":actual,
        "intermediate_ffv1_band_required":False,
    }
