"""Real FFmpeg one-frame watermark smoke, not a full math lesson render."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw
from animation_engine.brand_watermark import overlay_branding


def run(command):
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(
            f"FFMPEG_STATIC_ACCEPTANCE_FAILED({result.returncode}): "
            +result.stderr[-800:]
        )
    return result


def main():
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("STATIC_ACCEPTANCE_NEEDS_FFMPEG_FFPROBE")
    screenshot=Path(__file__).resolve().parents[2]/"frontend"/"screenshots"/"13-watermark-ffmpeg.png"
    screenshot.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wg-ffmpeg-one-frame-") as temp:
        path=Path(temp)
        canvas=Image.new("RGB",(1280,720),"white")
        draw=ImageDraw.Draw(canvas)
        draw.line([(64,108),(1216,108)],fill=(225,225,225),width=1)
        canvas.save(path/"board.png")
        original=path/"source.mp4"
        target=path/"branded.mp4"
        run([
            "ffmpeg","-hide_banner","-loglevel","error","-y",
            "-loop","1","-framerate","60","-i",str(path/"board.png"),
            "-f","lavfi","-i","anullsrc=r=24000:cl=mono",
            "-t","0.5","-c:v","libx264","-pix_fmt","yuv420p",
            "-c:a","aac",str(original),
        ])
        audit=overlay_branding(original,target,fps=60,frames=1)
        assert audit["position"]=="top_right"
        probe=run([
            "ffprobe","-v","error","-show_streams","-of","json",str(target),
        ])
        document=json.loads(probe.stdout)
        streams=document["streams"]
        video=next(s for s in streams if s.get("codec_type")=="video")
        audio=next(s for s in streams if s.get("codec_type")=="audio")
        assert video["width"]==1280 and video["height"]==720
        assert video["r_frame_rate"]=="60/1"
        assert int(audio["sample_rate"])>=16000
        run([
            "ffmpeg","-hide_banner","-loglevel","error","-y",
            "-i",str(target),"-frames:v","1",str(screenshot),
        ])
        assert screenshot.is_file() and screenshot.stat().st_size>1000
    print("STATIC_FFMPEG_WATERMARK_ACCEPTED",screenshot.name)


if __name__=="__main__":
    main()
