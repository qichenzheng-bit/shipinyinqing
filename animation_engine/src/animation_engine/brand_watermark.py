"""WeiGuang Math's quiet top-right classroom watermark.

Kept separate from the original lesson/MathTex content. The unaltered
source-exact video is muxed first; branding is an optional *final* overlay.
No image generation, external asset fetch or copyrighted font redistribution.
"""
from __future__ import annotations

import math
from pathlib import Path

BRAND_MARK_VERSION = "weiguang-book-star-graphite-gold-v1"
BRAND_INK = (68, 70, 73)
BRAND_GOLD = (176, 146, 82)
WATERMARK_WIDTH = 174
WATERMARK_HEIGHT = 48
WATERMARK_RIGHT_MARGIN = 22
WATERMARK_TOP_MARGIN = 14


def make_brand_watermark(output: Path, *, scale: float = 1.0) -> dict:
    """Render a transparent PNG with the user's open-book/star identity."""
    from PIL import Image, ImageDraw, ImageFont
    from .classroom_compositor import _cjk_font_path
    font_path = _cjk_font_path()
    if font_path is None:
        raise RuntimeError("BRAND_WATERMARK_CJK_FONT_UNAVAILABLE")
    mult = 4
    w = round(WATERMARK_WIDTH * mult * scale)
    h = round(WATERMARK_HEIGHT * mult * scale)
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    unit = mult * scale
    def v(p):
        return (round(p[0] * unit), round(p[1] * unit))
    def line(coords,fill,width=1):
        d.line([v(p) for p in coords], fill=fill,
               width=max(1,round(width*unit)),joint="curve")
    ink = (*BRAND_INK, 144)
    grey = (119, 120, 124, 109)
    gold = (*BRAND_GOLD, 163)

    # An intentionally simple small-size rendition of the existing open book.
    # Layer curves remain readable at a 174px-wide video watermark.
    line([(3,28),(12,24),(20,25),(29,32)],ink,2.9)
    line([(29,32),(37,25),(47,24),(56,28)],ink,2.9)
    line([(3,33),(15,30),(23,31),(29,36)],grey,2.3)
    line([(29,36),(36,31),(44,30),(56,33)],grey,2.3)
    line([(3,37),(16,34),(23,35),(29,40)],grey,1.5)
    line([(29,40),(36,35),(43,34),(56,37)],grey,1.5)
    # Four-point star, not a distracting full-color sticker.
    cx,cy,rad,thin=29,14,10,2.6
    d.polygon([v(p) for p in [
        (cx,cy-rad),(cx+thin,cy-thin),(cx+rad,cy),
        (cx+thin,cy+thin),(cx,cy+rad),(cx-thin,cy+thin),
        (cx-rad,cy),(cx-thin,cy-thin),
    ]], fill=gold)
    for dx,dy in [(-13,-8),(13,-8),(0,-13)]:
        p=(cx+dx,cy+dy)
        line([p,(p[0]+.8*(dx or 1)/abs(dx or 1),
                    p[1]+.8*(dy or 1)/abs(dy or 1))],grey,1)

    f = ImageFont.truetype(str(font_path), round(20*unit))
    d.text(v((62,10)), "微光数学", font=f, fill=ink,
           stroke_width=0)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.resize((round(w/mult),round(h/mult)), Image.Resampling.LANCZOS).save(path)
    return {
        "version": BRAND_MARK_VERSION,
        "position": "top_right",
        "right_margin_px_at_1280": WATERMARK_RIGHT_MARGIN,
        "top_margin_px_at_720": WATERMARK_TOP_MARGIN,
        "width_px_at_1280": WATERMARK_WIDTH,
        "opacity": "intrinsic transparent graphite + muted gold",
    }


def overlay_branding(
    source: Path, target: Path, *, fps: int, frames: int,
    runner=None,
) -> dict:
    """Overlay one badge on the actual complete movie, preserving audio."""
    import subprocess
    import shutil
    if not shutil.which("ffmpeg"):
        raise RuntimeError("BRAND_WATERMARK_FFMPEG_MISSING")
    source,target=Path(source),Path(target)
    if source.resolve()==target.resolve():
        raise ValueError("BRAND_WATERMARK_SOURCE_OUTPUT_ALIAS")
    if not isinstance(fps,int) or not 8<=fps<=60 or frames<=0:
        raise ValueError("BRAND_WATERMARK_INVALID_FRAME_RATE")
    mark=target.with_name(target.stem + ".watermark.png")
    info=make_brand_watermark(mark)
    command=[
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-i",str(source),"-loop","1","-framerate",str(fps),"-i",str(mark),
        "-filter_complex",
        f"[0:v][1:v]overlay=W-w-{WATERMARK_RIGHT_MARGIN}:{WATERMARK_TOP_MARGIN}"
        ":shortest=1:format=auto[v]",
        "-map","[v]","-map","0:a:0",
        "-c:v","libx264","-preset","veryfast","-crf","20",
        "-pix_fmt","yuv420p","-r",str(fps),
        "-frames:v",str(frames),"-c:a","copy",
        "-movflags","+faststart",str(target),
    ]
    try:
        if runner is not None:
            runner(command,"BRAND_WATERMARK_MUX_FAILED")
        else:
            p=subprocess.run(command,capture_output=True,text=True)
            if p.returncode != 0:
                raise RuntimeError("BRAND_WATERMARK_MUX_FAILED: " + p.stderr[-500:])
        if not target.is_file() or target.stat().st_size<1000:
            raise RuntimeError("BRAND_WATERMARK_OUTPUT_MISSING")
        return info
    finally:
        mark.unlink(missing_ok=True)
