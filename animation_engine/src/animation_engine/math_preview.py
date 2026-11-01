"""Render one approved formula to an actual white-background Manim PNG.

No teacher text, speech timing, moving equations, auto-wrap or video here.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .mathtex_renderer import MathTexRenderError, build_measured_mathtex
from .render_contract import MathRenderRequest


class MathPreviewError(ValueError):
    """Preview validation, overflow, or real rendering failure."""


@dataclass(frozen=True)
class MathPreviewResult:
    png_path: Path
    metadata_path: Path
    frame_width_px: int
    frame_height_px: int
    formula_bounds_px: tuple[float, float, float, float]


def render_math_preview(
    request: MathRenderRequest, *,
    output_png: Path,
    output_json: Path,
    pixel_width: int = 1280,
    pixel_height: int = 720,
) -> MathPreviewResult:
    if pixel_width < 320 or pixel_height < 180:
        raise MathPreviewError("INVALID_FRAME_SIZE: preview must be legible")
    from .safe_output import validate_output_targets, publish_bundle
    validate_output_targets({Path(output_png): ".png", Path(output_json): ".json"})
    if output_png.resolve() == output_json.resolve():
        raise MathPreviewError("INVALID_OUTPUT: PNG and metadata paths must differ")
    try:
        from manim import Camera, tempconfig
    except ImportError as exc:
        raise MathPreviewError("LATEX_ENV_UNAVAILABLE: Manim render extra not installed") from exc

    try:
        glyphs, metrics = build_measured_mathtex(request.latex, ink=request.theme.ink)
    except MathTexRenderError as exc:
        raise MathPreviewError(
            f"{exc}: event={request.event_id!r} object={request.object_id!r}"
        ) from exc

    fw = 8.0 * pixel_width / pixel_height
    fh = 8.0
    r = request.region
    safety = 0.13  # Manim world units; no unbounded downscaling.
    if (metrics.width_units + 2 * safety >= r.w * fw
            or metrics.height_units + 2 * safety >= r.h * fh):
        raise MathPreviewError(
            f"FORMULA_OVERFLOW: event={request.event_id!r} object={request.object_id!r} "
            f"math={metrics.width_units:.3f}x{metrics.height_units:.3f} "
            f"region={r.w * fw:.3f}x{r.h * fh:.3f}"
        )

    x = (r.x + r.w / 2 - .5) * fw
    y = (.5 - r.y - r.h / 2) * fh
    glyphs.move_to([x, y, 0])
    left = (glyphs.get_left()[0] / fw + .5) * pixel_width
    right = (glyphs.get_right()[0] / fw + .5) * pixel_width
    top = (.5 - glyphs.get_top()[1] / fh) * pixel_height
    bottom = (.5 - glyphs.get_bottom()[1] / fh) * pixel_height
    bounds = tuple(float(v) for v in (left, top, right, bottom))

    metadata = {
        "event_id": request.event_id,
        "object_id": request.object_id,
        "latex": request.latex,
        "source_step_ids": list(request.source_step_ids),
        "source_storyboard_sha256": request.source_storyboard_sha256,
        "region_name": request.region_name,
        "region": r.model_dump(mode="json"),
        "frame_width_px": pixel_width,
        "frame_height_px": pixel_height,
        "glyph_width_units": metrics.width_units,
        "glyph_height_units": metrics.height_units,
        "formula_bounds_px": list(bounds),
        "render_kind": "manim_mathtex_static_png",
    }

    output_png = Path(output_png)
    output_json = Path(output_json)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    # Render actual vector glyphs with Manim's Cairo camera, no surrogate text.
    # Render to a separate temporary file so failed rendering never leaves an
    # apparently successful preview.
    with tempfile.TemporaryDirectory(prefix="mathtex-preview-") as temp:
        temp_png = Path(temp) / "preview.png"
        temp_json = Path(temp) / "preview.json"
        try:
            with tempconfig({
                "pixel_width": pixel_width,
                "pixel_height": pixel_height,
                "frame_width": fw,
                "frame_height": fh,
                "background_color": request.theme.background,
            }):
                camera = Camera()
                camera.capture_mobjects([glyphs])
                image = camera.get_image()
                image.save(temp_png, format="PNG")
            temp_json.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            publish_bundle({
                output_png: temp_png, output_json: temp_json,
            }, suffixes={output_png: ".png", output_json: ".json"})
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            # Source and prior outputs remain intact after any failure.
            raise MathPreviewError(
                f"PREVIEW_RENDER_FAILED: event={request.event_id!r} object={request.object_id!r} "
                f"{type(exc).__name__}: {str(exc)[:180]}"
            ) from exc

    return MathPreviewResult(
        png_path=output_png, metadata_path=output_json,
        frame_width_px=pixel_width, frame_height_px=pixel_height,
        formula_bounds_px=bounds,
    )
