"""2.5.1 layout overlay on the genuine, source-checked 2.4 longboard.

The source of mathematical truth and page lifecycle remains build_longboard_plan.
We only reflow already validated/visible glyphs into overview, work, and result
bands. Failed group packing ALWAYS retains the valid original 2.4 placement.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from typing import Any, Callable

from visual_director.models import StoryboardPlan

from .adaptive_layout import GlyphSize, _overlap
from .calculation_group_models import validate_calculation_overlay
from .longboard_plan import (
    LongboardError, LongboardPolicy, _sha, build_longboard_plan,
)
from .models import ExecutionPlan


def _unique(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(x for group in groups for x in group))


def _reflow(
    placements: list[dict],
    zone: list[float],
    overview: list[str],
    results: list[str],
) -> list[dict] | None:
    """Reposition complete MathTex objects, never edit glyphs or their source."""
    if not placements:
        return placements
    by_id = {p["object_id"]: deepcopy(p) for p in placements}
    overview_set = set(overview)
    result_set = set(results)
    upper = [by_id[mid] for mid in overview if mid in by_id and mid not in result_set]
    bottom = [by_id[mid] for mid in results if mid in by_id]
    middle = [by_id[p["object_id"]] for p in placements
              if p["object_id"] not in overview_set | result_set]
    if not upper and not bottom:
        return None

    top = zone[1] + 11
    bottom_edge = zone[1] + zone[3] - 11
    gap = 15

    def height(rows: list[dict]) -> float:
        return sum(p["h"] for p in rows) + gap * max(0, len(rows) - 1)

    bottom_start = bottom_edge - height(bottom)
    # Keep explicit clearance between distinct regions, but do not reserve
    # a full empty row when one of them has no content.
    required = height(upper) + height(middle)
    if upper and middle:
        required += gap
    if bottom and (upper or middle):
        required += gap
    if top + required > bottom_start + .5:
        return None

    def position(rows: list[dict], y: float, role: str) -> None:
        for item in rows:
            delta = y - item["y"]
            item["y"] = round(y, 3)
            item["role"] = role
            for frag in item["fragments"]:
                frag["y"] = round(frag["y"] + delta, 3)
            y += item["h"] + gap

    position(upper, top, "group_overview")
    middle_top = top + height(upper) + (gap if upper and middle else 0)
    position(middle, middle_top, "group_working")
    position(bottom, bottom_start, "group_result")

    packed = {p["object_id"]: p for p in upper + middle + bottom}
    if set(packed) != set(by_id):
        raise LongboardError("CALC_INTERNAL_LOST_OBJECT")
    candidate = [packed[p["object_id"]] for p in placements]
    if any(
        p["y"] < zone[1] + 10.5 or p["y"] + p["h"] > zone[1] + zone[3] - 10.5
        for p in candidate
    ) or any(
        _overlap(candidate[i], candidate[j])
        for i in range(len(candidate)) for j in range(i + 1, len(candidate))
    ):
        return None
    return candidate


def _movements(row: dict, previous: dict[str, dict]) -> list[dict]:
    current = {p["object_id"]: p for p in row["placements"]}
    history = {m["object_id"]: m for m in row["movements"]}
    movements: list[dict] = []
    for mid, p in current.items():
        old = previous.get(mid)
        old_kind = history.get(mid, {}).get("kind", "carry")
        if old is None:
            kind = old_kind
        elif all(
            abs(old[k] - p[k]) < (0.0001 if k == "scale" else .5)
            for k in ("x", "y", "scale")
        ):
            kind = "hold"
        else:
            kind = "move"
        movements.append({
            "object_id": mid, "kind": kind,
            "previous_bbox": None if old is None else
                [old[k] for k in ("x", "y", "w", "h")],
            "target_bbox": [p[k] for k in ("x", "y", "w", "h")],
        })
    for mid, old in previous.items():
        if mid not in current:
            movements.append({
                "object_id": mid, "kind": "archive_from_view",
                "previous_bbox": [old[k] for k in ("x", "y", "w", "h")],
                "target_bbox": None,
            })
    return movements


def build_calculation_group_plan(
    storyboard: StoryboardPlan | dict[str, Any],
    execution: ExecutionPlan | dict[str, Any],
    *,
    overlay: dict[str, Any],
    policy: LongboardPolicy | dict | None = None,
    pixel_width: int = 1280,
    pixel_height: int = 720,
    measure: Callable[[str, int], GlyphSize] | None = None,
) -> dict:
    board = StoryboardPlan.model_validate(storyboard)
    source = ExecutionPlan.model_validate(execution)
    group = validate_calculation_overlay(overlay, source)
    source_policy = LongboardPolicy.parse(policy)
    source_policy.validate(
        {a.object_id for s in source.scenes for a in s.actions},
        {s.event_id for s in source.scenes},
        {a.object_id: {"latex": a.latex} for s in source.scenes for a in s.actions},
    )
    preferences = group.display_preferences
    overview = group.overview_object_ids
    results = _unique(*(p.result_object_ids for p in group.parts))

    # A large group must not permanently reserve more space for old
    # calculations than for the current teacher event. The 2.4 page planner
    # remains authoritative about when to archive/cut.
    keep_results = (
        results if len(results) <= preferences.max_retained_results else []
    )
    keep_overview = (
        overview if preferences.retain_overview
        and len(overview) <= preferences.max_overview_objects
        and group.group_kind != "dependent_chain" else []
    )
    if group.group_kind == "dependent_chain":
        keep_results = []

    attempts = [
        (keep_overview, keep_results, "preferred"),
        ([], keep_results, "overview_released"),
        ([], [], "longboard_capacity_fallback"),
    ]
    base = None
    fallback = None
    failure: LongboardError | None = None
    for add_overview, add_results, tag in attempts:
        combined = asdict(source_policy)
        combined["pinned_ids"] = _unique(
            list(source_policy.pinned_ids), add_overview,
        )
        combined["result_ids"] = _unique(
            list(source_policy.result_ids), add_results,
        )
        try:
            base = build_longboard_plan(
                board, source, policy=combined, pixel_width=pixel_width,
                pixel_height=pixel_height, measure=measure,
            )
            fallback = tag
            break
        except LongboardError as exc:
            if not (str(exc).startswith("PAGE_UNFIT")
                    or str(exc).startswith("LONG_FORMULA_UNFIT")):
                raise
            failure = exc
    if base is None:
        raise failure or LongboardError("CALC_PAGE_UNFIT")

    output = deepcopy(base)
    output["schema_version"] = "2.5.1-preview"
    output["base_longboard_sha256"] = output.pop("longboard_sha256")
    event_indices = {s.event_id: i for i, s in enumerate(source.scenes)}
    combine_set = set(group.combine_event_ids)
    final_intro = min(
        (next((i for i, scene in enumerate(source.scenes)
              if any(a.object_id == mid and a.kind == "progressive_write"
                     for a in scene.actions)), len(source.scenes))
         for mid in group.final_object_ids),
        default=len(source.scenes),
    )
    previous: dict[str, dict] = {}
    for row in output["events"]:
        idx = event_indices[row["event_id"]]
        active = next(
            (p for p in group.parts
             if event_indices[p.event_ids[0]] <= idx <= event_indices[p.event_ids[-1]]),
            None,
        )
        completed = [
            p.part_id for p in group.parts if event_indices[p.event_ids[-1]] <= idx
        ]
        if row["event_id"] in combine_set:
            phase = "combine"
        elif idx >= final_intro and group.final_object_ids:
            phase = "conclusion"
        elif active is not None:
            phase = "part_completed" if active.part_id in completed else "active_part"
        elif completed:
            phase = "between_parts"
        else:
            phase = "decomposition"

        # Stacked source data is already checked by the 2.4 planner. Only
        # repack placements it actually chose to display. Missing historical
        # objects are never resurrected to fill a decorative band.
        grouped = None
        if group.group_kind != "dependent_chain":
            grouped = _reflow(row["placements"], row["zone_px"], overview, results)
        if grouped is not None:
            row["placements"] = grouped
            row["layout_mode"] = "group_bands"
        else:
            row["layout_mode"] = "longboard_safe_fallback"
        row["group_state"] = {
            "phase": phase,
            "active_part_id": None if active is None else active.part_id,
            "completed_part_ids": completed,
            "visible_overview_ids": [
                p["object_id"] for p in row["placements"]
                if p["object_id"] in overview
            ],
            "visible_result_ids": [
                p["object_id"] for p in row["placements"]
                if p["object_id"] in results
            ],
        }
        row["movements"] = _movements(row, previous)
        previous = {p["object_id"]: p for p in row["placements"]}

    output["calculation_group"] = {
        "group_id": group.group_id,
        "group_kind": group.group_kind,
        "approval_reference": group.approval_reference,
        "source_execution_sha256": group.source_execution_sha256,
        "part_ids": [p.part_id for p in group.parts],
        "overview_object_ids": overview,
        "result_object_ids": results,
        "combine_event_ids": group.combine_event_ids,
        "final_object_ids": group.final_object_ids,
        "capacity_strategy": fallback,
        "display_only": True,
        "math_added_or_changed": False,
    }
    output["calculation_plan_sha256"] = _sha(output)
    return output
