"""Verified, pixel-measured, non-destructive classroom board layout (2.3).

This produces a *separate* layout overlay for immutable StoryboardPlan/ExecutionPlan.
It never creates equations, edits LaTeX, claims audio timing, or silently clips.
Full scrolling/cuts are explicitly handed to step 2.4.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from visual_director.models import Rect, StoryboardPlan
from .models import ExecutionPlan
from .planner import build_execution_plan
from .mathtex_renderer import MathTexRenderError, validate_math_latex


class AdaptiveLayoutError(ValueError):
    """A malformed source, unsafe formula, or failed layout render."""


@dataclass(frozen=True)
class GlyphSize:
    width_px: float
    height_px: float
    equals_x_px: float | None = None


# Minimum relative type size. Never shrink repeatedly across lesson events.
MIN_SCALE = 0.90
PADDING_X = 14.0
PADDING_Y = 11.0
ROW_GAP = 15.0
COLLISION_EPS = 0.8


def _real_measure(latex: str, pixel_height: int) -> GlyphSize:
    """Use the same true MathTex glyphs as the final static preview."""
    validate_math_latex(latex)
    try:
        from manim import MathTex, tempconfig
    except ImportError as exc:
        raise AdaptiveLayoutError("LATEX_ENV_UNAVAILABLE: install animation_engine[render]") from exc
    try:
        with tempconfig({"frame_height": 8.0, "frame_width": 8.0 * 16 / 9}):
            glyph = MathTex(latex, substrings_to_isolate=["="])
            px_per_unit = pixel_height / 8.0
            first_equals = next(
                (part for part in glyph.submobjects
                 if part.get_tex_string() == "="), None
            )
            offset = None if first_equals is None else (
                float(first_equals.get_center()[0] - glyph.get_left()[0]) * px_per_unit
            )
            return GlyphSize(
                float(glyph.width) * px_per_unit,
                float(glyph.height) * px_per_unit,
                offset,
            )
    except Exception as exc:
        raise AdaptiveLayoutError(
            f"TEX_MEASURE_FAILED: {type(exc).__name__}: {str(exc)[:200]}"
        ) from exc


def _to_pixels(zone: Rect, width: int, height: int) -> tuple[float, float, float, float]:
    return zone.x * width, zone.y * height, zone.w * width, zone.h * height


def _overlap(a: dict, b: dict) -> bool:
    return (a["x"] < b["x"] + b["w"] - COLLISION_EPS
            and b["x"] < a["x"] + a["w"] - COLLISION_EPS
            and a["y"] < b["y"] + b["h"] - COLLISION_EPS
            and b["y"] < a["y"] + a["h"] - COLLISION_EPS)


def _inside(p: dict, zone: tuple[float, float, float, float]) -> bool:
    x, y, w, h = zone
    return (p["x"] >= x + PADDING_X - COLLISION_EPS
            and p["y"] >= y + PADDING_Y - COLLISION_EPS
            and p["x"] + p["w"] <= x + w - PADDING_X + COLLISION_EPS
            and p["y"] + p["h"] <= y + h - PADDING_Y + COLLISION_EPS)


def _pack(
    rows: list[dict],
    areas: dict[str, Rect],
    measured: dict[str, GlyphSize],
    previous: dict[str, dict],
    width: int,
    height: int,
    mode: str,
) -> list[dict] | None:
    result: list[dict] = []
    for region in ("board", "scratch"):
        members = [row for row in rows if row["visual_region"] == region]
        if not members:
            continue
        if region not in areas:
            return None
        z = _to_pixels(areas[region], width, height)
        inner_width = z[2] - 2 * PADDING_X
        if inner_width <= 0:
            return None
        local: list[dict] = []
        # A visible item is retained in place whenever its verified glyph still fits.
        # A new item is appended below existing items, never suddenly inserted above.
        for item in members:
            old = previous.get(item["object_id"])
            m = measured[item["object_id"]]
            scale = min(1.0, inner_width / m.width_px) if m.width_px > 0 else 1.0
            if scale < MIN_SCALE - 1e-8:
                return None
            scale = max(MIN_SCALE, scale)
            w, h = m.width_px * scale, m.height_px * scale
            # Prefer exact old coordinates/scale when they are still safe.
            candidate = None
            if (old is not None and old["visual_region"] == region
                    and abs(old["w"] - w) < 0.5 and abs(old["h"] - h) < 0.5):
                candidate = dict(old)
                candidate.update(item)
                candidate["mode"] = mode
                if not _inside(candidate, z) or any(_overlap(candidate, a) for a in local):
                    candidate = None
            if candidate is None:
                x = z[0] + PADDING_X
                # Equals alignment is based on measured first "=" glyph, not
                # naive string slicing. Align to the first previously placed
                # comparable equation without rewriting either LaTeX.
                if m.equals_x_px is not None:
                    for earlier in local:
                        em = measured[earlier["object_id"]]
                        if em.equals_x_px is not None:
                            alignment_x = earlier["x"] + em.equals_x_px * earlier["scale"]
                            target_x = alignment_x - m.equals_x_px * scale
                            if (target_x >= z[0] + PADDING_X
                                    and target_x + w <= z[0] + z[2] - PADDING_X):
                                x = target_x
                            break
                y = max((p["y"] + p["h"] + ROW_GAP for p in local),
                        default=z[1] + PADDING_Y)
                candidate = {**item, "x": round(x, 3), "y": round(y, 3),
                             "w": round(w, 3), "h": round(h, 3),
                             "scale": round(scale, 6), "mode": mode}
                if not _inside(candidate, z) or any(_overlap(candidate, p) for p in local):
                    return None
            local.append(candidate)
        result.extend(local)
    if len(result) != len(rows):
        return None
    # Strong global check: no cross-zone collision, even when the source regions overlap.
    if any(_overlap(result[i], result[j]) for i in range(len(result))
           for j in range(i + 1, len(result))):
        return None
    return [next(p for p in result if p["object_id"] == row["object_id"]) for row in rows]


def _same_placement(a: dict, b: dict) -> bool:
    return (a["visual_region"] == b["visual_region"] and
            all(abs(a[k] - b[k]) < 0.5 for k in ("x", "y", "w", "h")))


def layout_storyboard(
    storyboard: StoryboardPlan | dict[str, Any],
    execution: ExecutionPlan | dict[str, Any],
    *,
    pixel_width: int = 1280,
    pixel_height: int = 720,
    measure: Callable[[str, int], GlyphSize] | None = None,
) -> dict[str, Any]:
    """Plan scenes with exact immutable sources; optional measure seam is for tests.

    A scene that cannot fit at >=90% size receives CUT_REQUIRED and no placements.
    This does not create an unauthorized cut or an incomplete rendered scene.
    """
    if pixel_width < 320 or pixel_height < 180:
        raise AdaptiveLayoutError("INVALID_FRAME_SIZE")
    try:
        board = StoryboardPlan.model_validate(storyboard)
        plan = ExecutionPlan.model_validate(execution)
        expected = build_execution_plan(board)
        if plan.model_dump(mode="json") != expected.model_dump(mode="json"):
            raise AdaptiveLayoutError("MISMATCH_EXECUTION_PLAN")
    except (ValueError, TypeError) as exc:
        raise AdaptiveLayoutError(f"MISMATCH_EXECUTION_PLAN: {exc}") from exc

    # Render-only operation; teacher/visual director object identity is immutable.
    originals: dict[str, dict] = {}
    for scene in plan.scenes:
        for action in scene.actions:
            if action.kind == "progressive_write":
                if action.object_id in originals and originals[action.object_id]["latex"] != action.latex:
                    raise AdaptiveLayoutError("MUTATED_MATH_OBJECT")
                originals.setdefault(action.object_id, {
                    "latex": action.latex,
                    "source_step_ids": list(action.source_step_ids),
                    "speech_unit_id": action.speech_unit_id,
                })
    size_of = measure or _real_measure
    measurements: dict[str, GlyphSize] = {}
    previous: dict[str, dict] = {}
    scene_results: list[dict] = []

    for scene in board.scenes:
        rows: list[dict] = []
        for object_id in scene.visible_ids:
            source = originals.get(object_id)
            if source is None:
                raise AdaptiveLayoutError(f"NO_ORIGINAL_FORMULA: {scene.event_id}/{object_id}")
            logical_region = scene.object_regions[object_id]
            if logical_region == "diagram":
                raise AdaptiveLayoutError("DIAGRAM_MATH_UNSUPPORTED: use geometry label renderer")
            if object_id not in measurements:
                try:
                    validate_math_latex(source["latex"])
                    m = size_of(source["latex"], pixel_height)
                except (MathTexRenderError, ValueError) as exc:
                    raise AdaptiveLayoutError(f"MEASURE_FAILED: {object_id}: {exc}") from exc
                if (not math.isfinite(m.width_px) or not math.isfinite(m.height_px)
                        or m.width_px <= 0 or m.height_px <= 0
                        or (m.equals_x_px is not None and
                            (not math.isfinite(m.equals_x_px)
                             or not 0 <= m.equals_x_px <= m.width_px))):
                    raise AdaptiveLayoutError(f"INVALID_GLYPH_METRICS: {object_id}")
                measurements[object_id] = m
            rows.append({"object_id": object_id, **source,
                         "logical_region": logical_region,
                         "visual_region": logical_region})

        # Try original board/scratch arrangement first.
        packed = _pack(rows, scene.regions, measurements, previous,
                       pixel_width, pixel_height, "original")
        mode = "original"
        # Scratch formulas like m_k_sin may be too wide for the right column.
        # Only expand into the union when no geometric diagram has this space.
        if packed is None and scene.layout == "split_scratch" and scene.diagram is None:
            zones = scene.regions
            left = min(zones["board"].x, zones["scratch"].x)
            right = max(zones["board"].x + zones["board"].w,
                        zones["scratch"].x + zones["scratch"].w)
            expanded = Rect(x=left, y=zones["board"].y,
                            w=right - left, h=zones["board"].h)
            expanded_rows = [{**row, "visual_region": "board"} for row in rows]
            packed = _pack(expanded_rows, {"board": expanded}, measurements,
                           previous, pixel_width, pixel_height, "expanded_scratch")
            mode = "expanded_scratch"
        if packed is None:
            scene_results.append({
                "event_id": scene.event_id, "status": "cut_required",
                "reason": "CUT_REQUIRED: measured math cannot fit at >=90% size",
                "mode": "no_valid_placement", "placements": [],
                "transitions": [], "sync_status": "semantic_anchors_only",
            })
            # A cut is for 2.4 to decide: never carry speculative coordinates.
            previous = {}
            continue

        transitions = []
        for p in packed:
            old = previous.get(p["object_id"])
            if old is None:
                kind = "appear"
            elif _same_placement(old, p):
                kind = "hold"
            else:
                kind = "move_at_action_boundary"
            transitions.append({
                "object_id": p["object_id"], "kind": kind,
                "from_bbox_px": None if old is None else
                    [old[k] for k in ("x", "y", "w", "h")],
                "to_bbox_px": [p[k] for k in ("x", "y", "w", "h")],
            })
        for object_id in previous:
            if object_id not in scene.visible_ids:
                transitions.append({
                    "object_id": object_id, "kind": "archive_or_remove",
                    "from_bbox_px": [previous[object_id][k] for k in ("x", "y", "w", "h")],
                    "to_bbox_px": None,
                })
        previous = {p["object_id"]: p for p in packed}
        scene_results.append({
            "event_id": scene.event_id, "status": "ready",
            "mode": mode, "placements": packed,
            "transitions": transitions,
            "sync_status": "semantic_anchors_only",
        })
    source = plan.source_storyboard_sha256
    body = {
        "schema_version": "2.3-preview",
        "source_storyboard_sha256": source,
        "source_package_sha256": plan.source_package_sha256,
        "frame_px": {"width": pixel_width, "height": pixel_height},
        "min_scale": MIN_SCALE,
        "timing_source": "semantic_anchors_only_not_audio_aligned",
        "header": board.header.model_dump(mode="json"),
        "scenes": scene_results,
    }
    body["layout_sha256"] = hashlib.sha256(json.dumps(
        body, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return body


def render_layout_png(
    storyboard: StoryboardPlan | dict[str, Any],
    execution: ExecutionPlan | dict[str, Any],
    *, event_id: str, output_png: Path, output_json: Path,
    pixel_width: int = 1280, pixel_height: int = 720,
) -> dict[str, Any]:
    """Render *all visible math* into a real Manim PNG; header/captions are reserved.

    Not yet the final Chinese header, subtitles or an audio-synchronized video.
    """
    if Path(output_png).resolve() == Path(output_json).resolve():
        raise AdaptiveLayoutError("INVALID_OUTPUT: preview and manifest overlap")
    board = StoryboardPlan.model_validate(storyboard)
    planned = layout_storyboard(board, execution,
                                pixel_width=pixel_width, pixel_height=pixel_height)
    scene = next((s for s in planned["scenes"] if s["event_id"] == event_id), None)
    if scene is None:
        raise AdaptiveLayoutError(f"UNKNOWN_EVENT: {event_id}")
    if scene["status"] != "ready":
        raise AdaptiveLayoutError(f"CUT_REQUIRED: {event_id}")
    try:
        from manim import Camera, MathTex, tempconfig
    except ImportError as exc:
        raise AdaptiveLayoutError("LATEX_ENV_UNAVAILABLE: install animation_engine[render]") from exc
    fw, fh = 8 * pixel_width / pixel_height, 8
    try:
        with tempfile.TemporaryDirectory(prefix="layout-2-3-") as tmp:
            temp_image = Path(tmp) / "board.png"
            with tempconfig({"pixel_width": pixel_width, "pixel_height": pixel_height,
                             "frame_width": fw, "frame_height": fh,
                             "background_color": board.theme.background}):
                glyphs = []
                for p in scene["placements"]:
                    obj = MathTex(p["latex"], substrings_to_isolate=["="],
                                  color=board.theme.ink)
                    obj.scale(p["scale"])
                    cx = p["x"] + p["w"] / 2
                    cy = p["y"] + p["h"] / 2
                    obj.move_to([(cx / pixel_width - 0.5) * fw,
                                 (0.5 - cy / pixel_height) * fh, 0])
                    actual = [float((obj.get_left()[0] / fw + .5) * pixel_width),
                              float((.5 - obj.get_top()[1] / fh) * pixel_height),
                              float(obj.width / fw * pixel_width),
                              float(obj.height / fh * pixel_height)]
                    if any(abs(a - p[k]) > 2 for a, k in
                           zip(actual, ("x", "y", "w", "h"))):
                        raise AdaptiveLayoutError(
                            f"RENDER_BOUNDS_MISMATCH: {event_id}/{p['object_id']}"
                        )
                    glyphs.append(obj)
                camera = Camera()
                camera.capture_mobjects(glyphs)
                camera.get_image().save(temp_image, format="PNG")
            output_png = Path(output_png)
            output_json = Path(output_json)
            output_png.parent.mkdir(parents=True, exist_ok=True)
            output_json.parent.mkdir(parents=True, exist_ok=True)
            payload = {**planned, "preview_event_id": event_id,
                       "preview_kind": "real_mathtex_static_layout",
                       "header_caption_status": "reserved_not_drawn"}
            temp_manifest = Path(tmp) / "manifest.json"
            temp_manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
            os.replace(temp_image, output_png)
            os.replace(temp_manifest, output_json)
            return payload
    except Exception:
        Path(output_png).unlink(missing_ok=True)
        Path(output_json).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="2.3 measured classroom layout preview")
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="Manifest JSON (or PNG with --event-id)")
    parser.add_argument("--event-id", help="Render a verified scene as true Manim PNG")
    parser.add_argument("--manifest", type=Path, help="Required with --event-id")
    opts = parser.parse_args(argv)
    try:
        board = json.loads(opts.storyboard.read_text(encoding="utf-8"))
        plan = json.loads(opts.execution.read_text(encoding="utf-8"))
        if opts.event_id:
            if opts.manifest is None:
                parser.error("--manifest is required with --event-id")
            render_layout_png(board, plan, event_id=opts.event_id,
                              output_png=opts.output, output_json=opts.manifest)
        else:
            if opts.manifest is not None or opts.output.suffix.lower() != ".json":
                parser.error("plan mode writes --output .json and needs no --manifest")
            layout = layout_storyboard(board, plan)
            opts.output.parent.mkdir(parents=True, exist_ok=True)
            opts.output.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Adaptive layout failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
