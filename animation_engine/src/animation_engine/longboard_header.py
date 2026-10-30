"""Fixed original question raster overlay for 2.4 Manim long-board preview.

Mathematics remains actual MathTex and CJK is rasterized using an actual CJK
font. The question is taken verbatim from the approved StoryboardPlan header;
missing/unrepresentable formats fail closed instead of displaying fake symbols.
"""
from __future__ import annotations

from pathlib import Path

from .adaptive_layout import AdaptiveLayoutError
from .classroom_compositor import _source_parts, _font


def make_question_overlay(storyboard, destination: Path, *,
                          pixel_width: int = 1280, pixel_height: int = 720,
                          compact: bool = False,
                          ink_color: str | None = None) -> dict:
    from visual_director.models import StoryboardPlan
    from PIL import Image, ImageDraw, ImageChops

    board = StoryboardPlan.model_validate(storyboard)
    ink_color = ink_color or board.theme.ink
    first = board.scenes[0]
    for scene in board.scenes:
        if scene.regions.get("question") != first.regions.get("question"):
            raise AdaptiveLayoutError(
                "HEADER_REGION_CHANGED: fixed question cannot shift mid-lesson"
            )
    zone = first.regions["question"]
    text_part, math_part, suffix = _source_parts(board.header.text)
    left = zone.x * pixel_width
    top = zone.y * pixel_height
    width = zone.w * pixel_width
    height = zone.h * pixel_height
    padding = 6
    opaque = Image.new("RGBA", (pixel_width, pixel_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(opaque)
    font = _font((20 if compact else 31) if pixel_height >= 600 else max(17, pixel_height//25))
    math_sprite = None
    if math_part:
        try:
            from manim import MathTex, Camera, tempconfig
        except ImportError as exc:
            raise AdaptiveLayoutError("LATEX_ENV_UNAVAILABLE") from exc
        fw, fh = 8*pixel_width/pixel_height, 8.
        with tempconfig({"pixel_width": pixel_width, "pixel_height": pixel_height,
                         "frame_width": fw, "frame_height": fh,
                         "background_color": board.theme.background}):
            glyph = MathTex(math_part, color=ink_color, font_size=(27 if compact else 34))
            glyph.move_to([0,0,0])
            camera = Camera()
            camera.capture_mobjects([glyph])
            image = camera.get_image().convert("RGB")
            x0 = max(0, int((glyph.get_left()[0]/fw+.5)*pixel_width)-2)
            x1 = min(pixel_width, int((glyph.get_right()[0]/fw+.5)*pixel_width)+3)
            y0 = max(0, int((.5-glyph.get_top()[1]/fh)*pixel_height)-2)
            y1 = min(pixel_height, int((.5-glyph.get_bottom()[1]/fh)*pixel_height)+3)
            if x1<=x0 or y1<=y0:
                raise AdaptiveLayoutError("HEADER_MATH_BOUNDS")
            sprite_rgb = image.crop((x0,y0,x1,y1))
            alpha = ImageChops.difference(
                sprite_rgb, Image.new("RGB", sprite_rgb.size, board.theme.background)
            ).convert("L")
            # Preserve true math glyph antialiasing against the transparent board.
            math_sprite = sprite_rgb.convert("RGBA")
            math_sprite.putalpha(alpha)

    def bounds(ft):
        a = draw.textbbox((0,0), text_part, font=ft)
        b = draw.textbbox((0,0), suffix, font=ft)
        return ((a[2]-a[0], a[3]-a[1], a[1]),
                (b[2]-b[0], b[3]-b[1], b[1]))

    t, s = bounds(font)
    mw, mh = math_sprite.size if math_sprite is not None else (0, 0)
    gap = 18 if math_sprite is not None else 0
    natural_width = t[0]+mw+s[0]+gap
    natural_height = max(t[1], mh, s[1])
    if natural_width <= 0 or natural_height <= 0:
        raise AdaptiveLayoutError("HEADER_EMPTY")
    factor = min(1., (width-2*padding)/natural_width,
                 (height-2*padding)/natural_height)
    if factor < .90-1e-8:
        raise AdaptiveLayoutError(
            "HEADER_OVERFLOW: long question needs teacher-approved split/header layout"
        )
    if factor < 1:
        font = _font(max(16, round(font.size*factor)))
        t, s = bounds(font)
        if math_sprite is not None:
            math_sprite = math_sprite.resize(
                (max(1,round(mw*factor)),max(1,round(mh*factor))),
                Image.Resampling.LANCZOS)
            mw,mh = math_sprite.size
        natural_width = t[0]+mw+s[0]+gap
        natural_height = max(t[1], mh, s[1])
        if natural_width > width-2*padding+1 or natural_height > height-2*padding+1:
            raise AdaptiveLayoutError("HEADER_OVERFLOW: conservative font adjustment")
    x = left + ((width-natural_width)/2 if board.header.align == "center" else padding)
    mid_y = top + height/2
    if text_part:
        draw.text((round(x),round(mid_y-t[1]/2-t[2])), text_part,
                  font=font, fill=ink_color)
    x += t[0]
    if math_sprite is not None:
        x += gap/2
        opaque.alpha_composite(math_sprite, (round(x), round(mid_y-mh/2)))
        x += mw+gap/2
    if suffix:
        draw.text((round(x),round(mid_y-s[1]/2-s[2])), suffix,
                  font=font, fill=ink_color)
    # After drawing, *every visible pixel* must remain in the approved header.
    alpha_box = opaque.getchannel("A").getbbox()
    if (alpha_box is None or alpha_box[0] < left-2 or alpha_box[1] < top-2
            or alpha_box[2] > left+width+2 or alpha_box[3] > top+height+2):
        raise AdaptiveLayoutError("HEADER_OVERFLOW: actual glyphs breached safe region")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    opaque.save(destination)
    return {
        "question_exact_source": board.header.text,
        "header_bbox_px": [round(left),round(top),round(width),round(height)],
        "visible_pixel_bbox": list(alpha_box),
        "scale": round(factor,6),
        "style": "compact_question" if compact else "classic_question",
        "math_latex": math_part,
        "ink_color": ink_color,
        "subtitle_status": "reserved_not_rendered",
    }
