"""2.4 long-board pagination: source-verified, deterministic, never invents mathematics.

A *display page* is distinct from a teacher event. A page may carry mathematical
objects previously shown, but may not alter their LaTeX, source steps, speech
anchors, or upstream lifecycle. No event is silently skipped. Every automatic
archive is a presentation operation; teacher removals remain authoritative.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Callable

from visual_director.models import StoryboardPlan
from .models import ExecutionPlan
from .planner import build_execution_plan
from .adaptive_layout import GlyphSize, _real_measure, _overlap
from .mathtex_renderer import validate_math_latex


class LongboardError(ValueError):
    """Explicit, source-addressed layout failure; never silently truncate."""


@dataclass(frozen=True)
class LongboardPolicy:
    # The creator/teacher must explicitly name semantically important results.
    pinned_ids: tuple[str, ...] = ()
    result_ids: tuple[str, ...] = ()
    # Exact source-LaTeX slices that must concatenate byte-for-byte to source.
    break_hints: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Optional user-authorized page boundaries. Never at a math fragment boundary.
    cut_before_events: tuple[str, ...] = ()
    allow_scroll: bool = True
    max_scrolls_per_page: int = 2
    max_scroll_fraction: float = 0.48
    carry_count: int = 1
    full_width_without_diagram: bool = True

    @classmethod
    def parse(cls, value: "LongboardPolicy | dict | None") -> "LongboardPolicy":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise LongboardError("INVALID_POLICY: expected JSON object")
        permitted = {
            "pinned_ids", "result_ids", "break_hints", "cut_before_events",
            "allow_scroll", "max_scrolls_per_page", "max_scroll_fraction",
            "carry_count", "full_width_without_diagram",
        }
        if set(value) - permitted:
            raise LongboardError("INVALID_POLICY: unknown keys " + str(sorted(set(value)-permitted)))
        try:
            return cls(
                pinned_ids=tuple(value.get("pinned_ids", [])),
                result_ids=tuple(value.get("result_ids", [])),
                break_hints={k: tuple(v) for k, v in value.get("break_hints", {}).items()},
                cut_before_events=tuple(value.get("cut_before_events", [])),
                allow_scroll=value.get("allow_scroll", True),
                max_scrolls_per_page=value.get("max_scrolls_per_page", 2),
                max_scroll_fraction=value.get("max_scroll_fraction", .48),
                carry_count=value.get("carry_count", 1),
                full_width_without_diagram=value.get("full_width_without_diagram", True),
            )
        except (TypeError, ValueError) as exc:
            raise LongboardError(f"INVALID_POLICY: {exc}") from exc

    def validate(self, object_ids: set[str], event_ids: set[str], originals: dict[str, dict]):
        for name, ids, domain in (
            ("pinned_ids", self.pinned_ids, object_ids),
            ("result_ids", self.result_ids, object_ids),
            ("cut_before_events", self.cut_before_events, event_ids),
        ):
            if any(type(i) is not str or i not in domain for i in ids) or len(ids) != len(set(ids)):
                raise LongboardError(f"INVALID_POLICY: {name} contains duplicate/unknown ID")
        if set(self.break_hints) - object_ids:
            raise LongboardError("INVALID_POLICY: break_hints reference unknown object")
        if (type(self.allow_scroll) is not bool
                or type(self.full_width_without_diagram) is not bool
                or type(self.max_scrolls_per_page) is not int
                or not 0 <= self.max_scrolls_per_page <= 20
                or type(self.carry_count) is not int or not 0 <= self.carry_count <= 10
                or type(self.max_scroll_fraction) not in (int, float)
                or not math.isfinite(self.max_scroll_fraction)
                or not 0 < self.max_scroll_fraction <= 1):
            raise LongboardError("INVALID_POLICY: invalid scroll/carry limits")
        for object_id, parts in self.break_hints.items():
            original = originals[object_id]["latex"]
            if (not parts or len(parts) < 2
                    or any(type(p) is not str or not p for p in parts)
                    or "".join(parts) != original):
                raise LongboardError(f"UNSAFE_BREAK: {object_id} does not reconstruct source LaTeX")
            if "\\begin{" in original or "\\end{" in original:
                raise LongboardError(f"UNSAFE_BREAK: cannot split a matrix/environment {object_id}")
            for part in parts:
                try:
                    validate_math_latex(part)
                except ValueError as exc:
                    raise LongboardError(f"UNSAFE_BREAK: {object_id}: {exc}") from exc


def _sha(value: dict) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _sources(plan: ExecutionPlan) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for scene in plan.scenes:
        for action in scene.actions:
            object_id = action.object_id
            signature = {
                "latex": action.latex,
                "source_step_ids": list(action.source_step_ids),
                "speech_unit_id": action.speech_unit_id,
            }
            if object_id in records:
                before = records[object_id]
                if (before["latex"] != signature["latex"]
                        or before["source_step_ids"] != signature["source_step_ids"]):
                    raise LongboardError(f"SOURCE_MUTATED: {object_id}")
            else:
                records[object_id] = signature
    return records


def _workspace(scene, width: int, height: int, full_width: bool):
    z = scene.regions.get("board")
    if z is None:
        raise LongboardError(f"NO_BOARD_REGION: {scene.event_id}")
    x1, x2 = z.x, z.x + z.w
    if scene.diagram is None and full_width and "scratch" in scene.regions:
        scratch = scene.regions["scratch"]
        x1 = min(x1, scratch.x)
        x2 = max(x2, scratch.x + scratch.w)
    return (round(x1 * width, 3), round(z.y * height, 3),
            round((x2-x1) * width, 3), round(z.h * height, 3))


def _size_parts(object_id: str, source: dict, policy: LongboardPolicy,
                measure: Callable[[str, int], GlyphSize], frame_height: int,
                cache: dict[str, dict]) -> dict:
    if object_id not in cache:
        parts = policy.break_hints.get(object_id, (source["latex"],))
        metrics = []
        for chunk in parts:
            validate_math_latex(chunk)
            raw = measure(chunk, frame_height)
            if (not isinstance(raw, GlyphSize)
                    or not math.isfinite(raw.width_px) or not math.isfinite(raw.height_px)
                    or raw.width_px <= 0 or raw.height_px <= 0):
                raise LongboardError(f"INVALID_METRICS: {object_id}")
            metrics.append(raw)
        cache[object_id] = {
            "segments": list(parts),
            "metrics": metrics,
            "height": sum(x.height_px for x in metrics) + 10 * (len(metrics)-1),
            "width": max(x.width_px for x in metrics),
        }
    return cache[object_id]


def _make_placement(object_id: str, source: dict, measured: dict,
                    x: float, y: float, available_width: float,
                    frame: tuple[int, int], role: str) -> dict:
    # One common scale across every fragment: never distort fractions/matrices.
    scale = min(1., available_width / measured["width"])
    if scale < .90 - 1e-8:
        raise LongboardError(
            f"LONG_FORMULA_UNFIT: {object_id}; requires authorized break_hints"
        )
    scale = max(.90, scale)
    px, py = x, y
    fragments = []
    for i, (chunk, metric) in enumerate(zip(measured["segments"], measured["metrics"])):
        rect = {"latex": chunk, "fragment_index": i, "x": round(px, 3),
                "y": round(py, 3), "w": round(metric.width_px*scale, 3),
                "h": round(metric.height_px*scale, 3)}
        fragments.append(rect)
        py += metric.height_px * scale + (10 if i < len(measured["segments"])-1 else 0)
    h = py - y
    result = {
        "object_id": object_id, "latex": source["latex"],
        "source_step_ids": list(source["source_step_ids"]),
        "speech_unit_id": source["speech_unit_id"],
        "role": role, "x": round(x, 3), "y": round(y, 3),
        "w": round(max(part["w"] for part in fragments), 3),
        "h": round(h, 3), "scale": round(scale, 6),
        "fragments": fragments,
    }
    if (x < 0 or x+result["w"] > frame[0]+.5):
        raise LongboardError(f"FRAME_OVERFLOW: {object_id}")
    return result


def _arrange(ids: list[str], fixed: list[str], sources: dict, cache: dict,
             size_of: Callable[[str, int], GlyphSize], policy: LongboardPolicy,
             zone: tuple[float, float, float, float],
             frame: tuple[int, int]) -> list[dict] | None:
    x, y, w, h = zone
    pad_x, pad_y, gap = 14, 11, 15
    if w <= 2*pad_x or h <= 2*pad_y:
        return None
    placements: list[dict] = []
    cursor = y + pad_y
    for role, ordered in (("fixed", fixed), ("working", ids)):
        for object_id in ordered:
            metrics = _size_parts(object_id, sources[object_id], policy,
                                  size_of, frame[1], cache)
            item = _make_placement(object_id, sources[object_id], metrics,
                                   x+pad_x, cursor, w-2*pad_x, frame, role)
            if item["y"]+item["h"] > y+h-pad_y + .5:
                return None
            if any(_overlap(item, other) for other in placements):
                raise LongboardError(f"INTERNAL_COLLISION: {object_id}")
            placements.append(item)
            cursor += item["h"]+gap
        if role == "fixed" and ordered and ids:
            cursor += 13
    return placements


def build_longboard_plan(
    storyboard: StoryboardPlan | dict[str, Any],
    execution: ExecutionPlan | dict[str, Any], *,
    policy: LongboardPolicy | dict[str, Any] | None = None,
    pixel_width: int = 1280, pixel_height: int = 720,
    measure: Callable[[str, int], GlyphSize] | None = None,
) -> dict:
    """Compute a full page/scroll/carry overlay; do not render or create TeX.

    At each complete event boundary:
      1) keep everything if it fits;
      2) slide oldest completed working objects out if a short scroll is enough;
      3) cut, carrying explicitly pinned results and recent context;
      4) fail closed if even a fresh page cannot fit the complete event.
    """
    if (type(pixel_width) is not int or type(pixel_height) is not int
            or pixel_width < 320 or pixel_height < 180):
        raise LongboardError("INVALID_FRAME_SIZE")
    try:
        board = StoryboardPlan.model_validate(storyboard)
        source_plan = ExecutionPlan.model_validate(execution)
        if source_plan.model_dump(mode="json") != build_execution_plan(board).model_dump(mode="json"):
            raise LongboardError("SOURCE_CONTRACT_MISMATCH")
    except (ValueError, TypeError) as exc:
        raise LongboardError(f"SOURCE_CONTRACT_MISMATCH: {exc}") from exc
    sources = _sources(source_plan)
    event_ids = {s.event_id for s in board.scenes}
    selected = LongboardPolicy.parse(policy)
    selected.validate(set(sources), event_ids, sources)
    size_of = measure or _real_measure
    frame = (pixel_width, pixel_height)
    page_number, scrolls = 1, 0
    previous: dict[str, dict] = {}
    last_seen: set[str] = set()
    auto_archived: set[str] = set()
    cache: dict[str, dict] = {}
    pages: list[dict] = []
    events: list[dict] = []

    for scene, execution_scene in zip(board.scenes, source_plan.scenes):
        for action in execution_scene.actions:
            if action.kind == "archive" and action.source_action == "automatic_state_change":
                auto_archived.add(action.object_id)
            if action.kind in ("remove", "restore"):
                auto_archived.discard(action.object_id)
        visible = list(scene.visible_ids)
        # Only explicitly pinned objects may survive the director's automatic
        # capacity-based archive. A teacher-directed remove is never overridden.
        fixed = [mid for mid in dict.fromkeys(
            selected.pinned_ids + selected.result_ids)
            if mid in visible or (mid in scene.archived_ids and mid in auto_archived
                                  and mid in last_seen)]
        working = [mid for mid in visible if mid not in fixed]
        new_ids = [a.object_id for a in execution_scene.actions
                   if a.kind in ("progressive_write", "restore")
                   and a.object_id in working + fixed]
        # Headline/highlight-only events do not count as newly written maths.
        new_ids = list(dict.fromkeys(new_ids))
        zone = _workspace(scene, *frame, selected.full_width_without_diagram)
        if scene.diagram is not None and any(scene.object_regions.get(mid) == "diagram"
                                             for mid in visible):
            raise LongboardError(f"DIAGRAM_LAYOUT_UNSUPPORTED: {scene.event_id}")
        all_placements = _arrange(working, fixed, sources, cache, size_of,
                                  selected, zone, frame)
        old_page = page_number
        mode = "hold" if not new_ids else "append"
        hidden_by_layout: list[str] = []
        if (all_placements is None or scene.event_id in selected.cut_before_events):
            # Only scroll away complete *previously displayed* work, never a
            # newly taught object or a pinned result.
            remaining = list(working)
            scrolling = None
            if (selected.allow_scroll and all_placements is None
                    and scrolls < selected.max_scrolls_per_page):
                removed = []
                for mid in working:
                    if mid in new_ids or mid not in previous:
                        break
                    removed.append(mid)
                    remaining.remove(mid)
                    possible = _arrange(remaining, fixed, sources, cache,
                                        size_of, selected, zone, frame)
                    if possible is not None:
                        distance = sum(previous[m]["h"]+15 for m in removed)
                        if distance <= selected.max_scroll_fraction * zone[3]:
                            scrolling = possible
                            hidden_by_layout = list(removed)
                        break
            if scrolling is not None:
                all_placements = scrolling
                mode = "scroll"
                scrolls += 1
            else:
                # A clean page may carry a small tail of previous working
                # context, but its initial viewport must be wholly valid.
                page_number += 1 if events else 0
                scrolls = 0
                mode = "cut" if events else "append"
                retained = [mid for mid in working
                            if mid not in new_ids and mid in previous]
                carry = retained[-selected.carry_count:] if selected.carry_count else []
                proposed = list(dict.fromkeys(carry+new_ids))
                all_placements = _arrange(proposed, fixed, sources, cache, size_of,
                                          selected, zone, frame)
                while all_placements is None and carry:
                    carry.pop(0)
                    proposed = list(dict.fromkeys(carry+new_ids))
                    all_placements = _arrange(proposed, fixed, sources, cache, size_of,
                                              selected, zone, frame)
                if all_placements is None:
                    raise LongboardError(
                        f"PAGE_UNFIT: {scene.event_id}; pinned + complete new actions "
                        "do not fit even on a clean page"
                    )
                hidden_by_layout = [mid for mid in working if mid not in proposed]
        assert all_placements is not None
        placed = {p["object_id"]: p for p in all_placements}
        movements = []
        for p in all_placements:
            mid = p["object_id"]
            old = previous.get(mid)
            if mid in new_ids and mid not in last_seen:
                how = "write"
            elif old is None:
                how = "restore_from_history" if mid in last_seen else "carry"
            elif old["x"] == p["x"] and old["y"] == p["y"] and old["scale"] == p["scale"]:
                how = "hold"
            else:
                how = "move"
            movements.append({
                "object_id": mid, "kind": how,
                "previous_bbox": None if old is None else
                    [old[k] for k in ("x", "y", "w", "h")],
                "target_bbox": [p[k] for k in ("x", "y", "w", "h")],
            })
        for mid in previous:
            if mid not in placed:
                movements.append({
                    "object_id": mid, "kind": "archive_from_view",
                    "previous_bbox": [previous[mid][k] for k in ("x","y","w","h")],
                    "target_bbox": None,
                })
        for mid in hidden_by_layout:
            if mid not in last_seen and mid not in previous:
                raise LongboardError(
                    f"UNSEEN_CONTENT_HIDDEN: {scene.event_id}/{mid}"
                )
        # All newly introduced teacher math must be rendered in this event.
        if any(mid not in last_seen and mid not in new_ids
               for mid in fixed + working):
            # A visual archive must never hide first-time teacher content.
            raise LongboardError(f"UNSEEN_CONTENT: {scene.event_id}")
        if set(new_ids) - set(placed):
            raise LongboardError(f"NEW_CONTENT_SKIPPED: {scene.event_id}")
        if mode == "cut":
            pages.append({
                "page_index": old_page, "ended_before_event_id": scene.event_id,
            })
        entry = {
            "event_id": scene.event_id, "page_index": page_number,
            "transition": mode,
            "zone_px": list(zone),
            "fixed_ids": [mid for mid in fixed if mid in placed],
            "active_ids": [mid for mid in working if mid in placed],
            "new_ids": new_ids, "display_archived_ids": hidden_by_layout,
            "placements": all_placements, "movements": movements,
            "source_state_sha256": execution_scene.state_sha256,
            "sync_status": "semantic_anchors_only_not_audio_aligned",
        }
        events.append(entry)
        previous = placed
        last_seen.update(placed)
    if events:
        pages.append({"page_index": page_number, "ended_before_event_id": None})
    result = {
        "schema_version": "2.4-preview",
        "source_storyboard_sha256": source_plan.source_storyboard_sha256,
        "source_package_sha256": source_plan.source_package_sha256,
        "frame_px": {"width": pixel_width, "height": pixel_height},
        "policy": {
            "pinned_ids": list(selected.pinned_ids),
            "result_ids": list(selected.result_ids),
            "break_hints": {k:list(v) for k,v in selected.break_hints.items()},
            "cut_before_events": list(selected.cut_before_events),
            "allow_scroll": selected.allow_scroll,
            "max_scrolls_per_page": selected.max_scrolls_per_page,
            "max_scroll_fraction": selected.max_scroll_fraction,
            "carry_count": selected.carry_count,
            "full_width_without_diagram": selected.full_width_without_diagram,
        },
        "pages": pages, "events": events,
        "timing_source": "preview_only_not_audio_aligned",
    }
    result["longboard_sha256"] = _sha(result)
    return result
