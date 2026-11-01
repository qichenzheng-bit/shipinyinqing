"""Render each *actually voiced* subtitle phrase with genuine Manim MathTex.

Chinese parts use native CJK Text. Mathematical parts always use MathTex,
never a phonetic 'ai ke si' or unrendered TeX string on the screen.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .longboard_plan import LongboardError
from .mathtex_renderer import validate_math_latex


def render_caption_png(kind: str, display: str, output: Path) -> None:
    if kind not in ("text","math") or not display:
        raise LongboardError("CAPTION_UNVERIFIED_SOURCE")
    if kind=="math":
        validate_math_latex(display)
    elif any(x in display for x in ("\\","$","{","}")):
        raise LongboardError("CAPTION_PHONETIC_OR_RAW_TEX")
    try:
        from manim import (
            Scene, Text, MathTex, RoundedRectangle, VGroup,
            WHITE, BLACK, tempconfig
        )
    except ImportError as exc:
        raise LongboardError("CAPTION_MANIM_REQUIRED") from exc

    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="math-caption-") as tmp:
        root=Path(tmp)
        with tempconfig({
            "pixel_width":1280,"pixel_height":720,
            "frame_width":1280/90,"frame_height":8,
            "frame_rate":30, "background_color":"#FFFFFF",
            "transparent":True, "format":"png",
            "save_last_frame":True,"media_dir":str(root),
            "output_file":"source_math_subtitle",
            "disable_caching":True,
        }):
            class CaptionScene(Scene):
                def construct(self):
                    if kind=="math":
                        glyph=MathTex(display,color=BLACK).scale(.53)
                    else:
                        glyph=Text(
                            display,font="Noto Sans CJK SC",
                            color="#111827",font_size=23,
                        )
                    if glyph.width>12.6 or glyph.height>.47:
                        raise LongboardError("CAPTION_LINE_TOO_LONG")
                    glyph.move_to([0,-3.53,0])
                    plate=RoundedRectangle(
                        width=max(1.0,glyph.width+.36),
                        height=.56,corner_radius=.09,
                        fill_color=WHITE,fill_opacity=.97,
                        stroke_color="#CBD5E1",stroke_width=.35,
                    ).move_to([0,-3.53,0])
                    self.add(plate,glyph)
            scene=CaptionScene()
            scene.render()
            matches=list(root.rglob("source_math_subtitle.png"))
            if len(matches)!=1 or matches[0].stat().st_size<100:
                raise LongboardError("CAPTION_REAL_MATHTEX_PNG_MISSING")
            from PIL import Image
            source=Image.open(matches[0]).convert("RGBA")
            if source.size != (1280,720):
                raise LongboardError("CAPTION_RENDERED_FRAME_SIZE")
            # Source MathTex was rendered on the real classroom canvas,
            # but only the 88px safe subtitle band should be streamed
            # into FFmpeg.  Avoid compositing a 720p overlay per phrase.
            source.crop((0,628,1280,716)).save(output)


def captions_srt(cues: list[dict], *, fps: int) -> str:
    def fmt(frame):
        ms=round(frame*1000/fps)
        hh,ms=divmod(ms,3600000)
        mm,ms=divmod(ms,60000)
        ss,ms=divmod(ms,1000)
        return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"
    result=[]
    for i,cue in enumerate(cues,1):
        display=(
            r"\("+cue["display"]+r"\)"
            if cue["kind"]=="math" else cue["display"]
        )
        result.append(
            f'{i}\n{fmt(cue["start_frame"])} --> '
            f'{fmt(cue["end_frame"])}\n{display}\n'
        )
    return "\n".join(result)+"\n"
