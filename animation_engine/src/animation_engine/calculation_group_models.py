"""2.5.1 approved calculation relationships, never mathematical inference.

The overlay is a display-only, versioned contract. Its references MUST resolve to
the unchanged 2.4 storyboard/execution pair. Unreviewed relations are rejected.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .longboard_plan import LongboardError, _sha, _sources
from .models import ExecutionPlan


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CalculationPart(_Strict):
    part_id: str = Field(min_length=1)
    intro_event_id: str = Field(min_length=1)
    event_ids: list[str] = Field(min_length=1)
    input_object_ids: list[str] = Field(default_factory=list)
    working_object_ids: list[str] = Field(default_factory=list)
    result_object_ids: list[str] = Field(min_length=1)
    dependency_part_ids: list[str] = Field(default_factory=list)


class DisplayPreferences(_Strict):
    retain_overview: bool = True
    max_overview_objects: int = Field(default=3, ge=0, le=12)
    max_retained_results: int = Field(default=3, ge=0, le=12)


class CalculationGroupOverlay(_Strict):
    schema_version: Literal["1.0"] = "1.0"
    source_storyboard_sha256: str = Field(min_length=64, max_length=64)
    source_execution_sha256: str = Field(min_length=64, max_length=64)
    source_package_sha256: str = Field(min_length=64, max_length=64)
    approval: Literal["teacher_reviewed"]
    approval_reference: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    group_kind: Literal[
        "independent_sum", "conditional_cases", "alternative_methods",
        "dependent_chain",
    ]
    overview_object_ids: list[str] = Field(default_factory=list)
    parts: list[CalculationPart] = Field(min_length=2)
    combine_event_ids: list[str] = Field(default_factory=list)
    final_object_ids: list[str] = Field(default_factory=list)
    display_preferences: DisplayPreferences = Field(default_factory=DisplayPreferences)


def _unique(ids: list[str], name: str) -> None:
    if len(ids) != len(set(ids)) or any(not item.strip() for item in ids):
        raise LongboardError(f"CALC_DUPLICATE_OR_BLANK: {name}")


def validate_calculation_overlay(
    value: CalculationGroupOverlay | dict,
    execution: ExecutionPlan,
) -> CalculationGroupOverlay:
    """Reject stale, premature, ambiguous or unapproved display relations."""
    try:
        overlay = CalculationGroupOverlay.model_validate(value)
    except (ValueError, TypeError, ValidationError) as exc:
        raise LongboardError(f"CALC_OVERLAY_INVALID: {str(exc)[:350]}") from exc

    if (overlay.source_storyboard_sha256 != execution.source_storyboard_sha256
            or overlay.source_package_sha256 != execution.source_package_sha256
            or overlay.source_execution_sha256 != _sha(execution.model_dump(mode="json"))):
        raise LongboardError("CALC_SOURCE_MISMATCH: overlay does not match execution")
    events = {scene.event_id: i for i, scene in enumerate(execution.scenes)}
    sources = _sources(execution)
    first_write: dict[str, int] = {}
    removals: dict[str, list[int]] = {}
    for index, scene in enumerate(execution.scenes):
        for action in scene.actions:
            if action.kind == "progressive_write":
                first_write.setdefault(action.object_id, index)
            if action.kind == "remove":
                removals.setdefault(action.object_id, []).append(index)

    def check_objects(ids: list[str], label: str) -> None:
        _unique(ids, label)
        for mid in ids:
            if mid not in sources or mid not in first_write:
                raise LongboardError(f"CALC_UNKNOWN_OBJECT: {label}/{mid}")

    def check_events(ids: list[str], label: str) -> list[int]:
        _unique(ids, label)
        if any(eid not in events for eid in ids):
            raise LongboardError(f"CALC_UNKNOWN_EVENT: {label}")
        indices = [events[eid] for eid in ids]
        if indices != sorted(indices):
            raise LongboardError(f"CALC_EVENT_ORDER: {label}")
        return indices

    check_objects(overlay.overview_object_ids, "overview")
    check_objects(overlay.final_object_ids, "final")
    check_events(overlay.combine_event_ids, "combine")
    if overlay.group_kind == "independent_sum":
        if not overlay.combine_event_ids or not overlay.final_object_ids:
            raise LongboardError("CALC_SUM_NEEDS_SOURCE_COMBINATION")
    elif overlay.combine_event_ids:
        # The existing engine cannot prove that case/method combinations
        # are not being misrepresented as arithmetic addition.
        raise LongboardError("CALC_NON_SUM_COMBINATION_UNSUPPORTED")

    part_ids = [p.part_id for p in overlay.parts]
    _unique(part_ids, "parts")
    used_events: set[str] = set()
    result_ids: set[str] = set()
    previous_end = -1
    previous_parts: set[str] = set()
    for part in overlay.parts:
        indices = check_events(part.event_ids, part.part_id)
        if part.intro_event_id != part.event_ids[0] or indices[0] <= previous_end:
            raise LongboardError(f"CALC_PART_ORDER: {part.part_id}")
        if used_events.intersection(part.event_ids):
            raise LongboardError(f"CALC_PART_EVENT_OVERLAP: {part.part_id}")
        used_events.update(part.event_ids)
        previous_end = indices[-1]
        if part.dependency_part_ids != list(dict.fromkeys(part.dependency_part_ids)):
            raise LongboardError("CALC_DUPLICATE_DEPENDENCY")
        if set(part.dependency_part_ids) - previous_parts:
            raise LongboardError(f"CALC_FUTURE_DEPENDENCY: {part.part_id}")
        if overlay.group_kind == "independent_sum" and part.dependency_part_ids:
            raise LongboardError("CALC_DEPENDENT_SUM_PART")
        previous_parts.add(part.part_id)
        for label, ids in (
            ("input", part.input_object_ids), ("working", part.working_object_ids),
            ("result", part.result_object_ids),
        ):
            check_objects(ids, f"{part.part_id}/{label}")
        if result_ids.intersection(part.result_object_ids):
            raise LongboardError(f"CALC_RESULT_REUSED: {part.part_id}")
        result_ids.update(part.result_object_ids)
        for mid in part.result_object_ids:
            if first_write[mid] not in indices:
                raise LongboardError(f"CALC_PREMATURE_RESULT: {part.part_id}/{mid}")
        for mid in part.working_object_ids:
            if first_write[mid] not in indices:
                raise LongboardError(f"CALC_WORK_OUTSIDE_PART: {part.part_id}/{mid}")
        for mid in part.input_object_ids:
            if first_write[mid] > indices[-1]:
                raise LongboardError(f"CALC_FUTURE_INPUT: {part.part_id}/{mid}")
        for mid in part.result_object_ids:
            if any(index <= previous_end for index in removals.get(mid, [])):
                # A result that was deleted by its teacher cannot be kept.
                # The 2.4 renderer may archive it; teacher remove is stronger.
                raise LongboardError(f"CALC_REMOVED_RESULT: {part.part_id}/{mid}")

    first_part = events[overlay.parts[0].intro_event_id]
    if any(first_write[mid] > first_part for mid in overlay.overview_object_ids):
        raise LongboardError("CALC_FUTURE_OVERVIEW")
    if overlay.combine_event_ids:
        combine = check_events(overlay.combine_event_ids, "combine")
        if combine[0] <= previous_end:
            raise LongboardError("CALC_COMBINATION_BEFORE_PARTS_FINISH")
        if any(first_write[mid] < combine[0] for mid in overlay.final_object_ids):
            raise LongboardError("CALC_PREMATURE_FINAL")
    elif overlay.final_object_ids:
        if any(first_write[mid] <= previous_end for mid in overlay.final_object_ids):
            raise LongboardError("CALC_PREMATURE_FINAL")

    return overlay
