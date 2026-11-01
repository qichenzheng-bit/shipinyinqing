"""Source-exact fixed question overlay for persistent classroom video.

Math is rendered with authentic MathTex, including alternating prose/math
segments. Both the static preview and live-video overlay share one rasterizer.
"""
from __future__ import annotations

from pathlib import Path

from .adaptive_layout import AdaptiveLayoutError
from .classroom_compositor import _font
from .header_raster import render_source_header
from .safe_output import publish_bundle


def make_question_overlay(storyboard, destination: Path, *,
                          pixel_width: int = 1280, pixel_height: int = 720,
                          compact: bool = False,
                          ink_color: str | None = None) -> dict:
    from io import BytesIO
    from visual_director.models import StoryboardPlan

    board = StoryboardPlan.model_validate(storyboard)
    ink_color = ink_color or board.theme.ink
    first = board.scenes[0]
    for scene in board.scenes:
        if scene.regions.get("question") != first.regions.get("question"):
            raise AdaptiveLayoutError(
                "HEADER_REGION_CHANGED: fixed question cannot shift mid-lesson"
            )
    zone = first.regions["question"]
    overlay, layout = render_source_header(
        board.header.text,
        pixel_width=pixel_width, pixel_height=pixel_height,
        header_box=(
            zone.x * pixel_width, zone.y * pixel_height,
            zone.w * pixel_width, zone.h * pixel_height,
        ),
        font_loader=_font,
        font_size=((18 if compact else 31) if pixel_height >= 600
                   else max(17, pixel_height // 25)),
        math_font_size=(24 if compact else 34),
        ink_color=ink_color,
        background=board.theme.background,
        align=board.header.align, padding=6, min_scale=.90,
    )
    data = BytesIO()
    overlay.save(data, format="PNG")
    dest = Path(destination)
    publish_bundle({dest: data.getvalue()}, suffixes={dest: ".png"})
    maths = layout["math_segments_latex"]
    return {
        "question_exact_source": board.header.text,
        "header_bbox_px": layout["header_bbox_px"],
        "visible_pixel_bbox": layout["visible_pixel_bbox"],
        "scale": layout["scale"],
        "style": "compact_question" if compact else "classic_question",
        "math_latex": maths[0] if len(maths) == 1 else None,
        "math_segments_latex": maths,
        "source_segments": layout["source_segments"],
        "ink_color": ink_color,
        "subtitle_status": "reserved_not_rendered",
    }
