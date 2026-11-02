"""Multi-second genuine FFmpeg watermark acceptance, including preserved audio.

Catches the bug where a single-frame PNG ended a full MP4 after one frame.
No LLM, neural TTS, or artificial claim of a complete teaching lesson.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from animation_engine.brand_watermark import overlay_branding


def run(args):
    return subprocess.run(args,capture_output=True,text=True,check=True)


def main():
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("WATERMARK_SMOKE_REQUIRES_FFMPEG_FFPROBE")
    with tempfile.TemporaryDirectory(prefix="watermark-two-seconds-") as tmp:
        root=Path(tmp)
        board=root/"board.png"
        source=root/"source.mp4"
        branded=root/"branded.mp4"
        Image.new("RGB",(1280,720),(255,255,255)).save(board)
        run([
            "ffmpeg","-hide_banner","-loglevel","error","-y",
            "-loop","1","-framerate","60","-i",str(board),
            "-f","lavfi","-i","sine=frequency=440:sample_rate=24000",
            "-t","2","-map","0:v:0","-map","1:a:0",
            "-c:v","libx264","-pix_fmt","yuv420p","-r","60",
            "-frames:v","120","-c:a","aac","-b:a","96k",str(source),
        ])
        before=source.read_bytes()
        audit=overlay_branding(source,branded,fps=60,frames=120)
        assert audit["position"]=="top_right"
        assert source.read_bytes()==before
        probed=run([
            "ffprobe","-v","error","-count_frames","-show_streams",
            "-of","json",str(branded),
        ])
        streams=json.loads(probed.stdout)["streams"]
        video=next(x for x in streams if x.get("codec_type")=="video")
        audio=next(x for x in streams if x.get("codec_type")=="audio")
        assert (video["width"],video["height"])==(1280,720)
        assert video["r_frame_rate"]=="60/1"
        assert int(video["nb_read_frames"])==120,video
        assert int(audio["sample_rate"])==24000
        assert branded.stat().st_size>10000
        print("TWO_SECOND_BRANDED_VOICE_CARRIER_ACCEPTED",
              video["nb_read_frames"],"frames and",audio["sample_rate"],"Hz")


if __name__=="__main__":
    main()
