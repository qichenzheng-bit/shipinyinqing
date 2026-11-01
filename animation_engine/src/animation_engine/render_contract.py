"""Validate complete storyboard/animation provenance before selecting MathTex input.

A preview is never allowed to treat a header highlight as board content.
This module has no dependency on Manim or media code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from visual_director.models import Rect, StoryboardPlan, Theme
from .models import ExecutionPlan
from .planner import ExecutionError, build_execution_plan


class RenderContractError(ValueError):
    """Mismatched or non-visible mathematical render input."""


@dataclass(frozen=True)
class MathRenderRequest:
    event_id: str
    object_id: str
    latex: str
    region: Rect
    region_name: str
    theme: Theme
    source_storyboard_sha256: str
    source_step_ids: tuple[str, ...]


def select_math_render_request(
    storyboard: StoryboardPlan | dict[str, Any],
    execution: ExecutionPlan | dict[str, Any],
    *,
    event_id: str,
    object_id: str,
) -> MathRenderRequest:
    try:
        board = StoryboardPlan.model_validate(storyboard)
        supplied = ExecutionPlan.model_validate(execution)
        expected = build_execution_plan(board)
    except (ValueError, TypeError, ExecutionError) as exc:
        raise RenderContractError(f"MISMATCH_EXECUTION_PLAN: invalid input: {exc}") from exc

    if supplied.model_dump(mode="json") != expected.model_dump(mode="json"):
        raise RenderContractError("MISMATCH_EXECUTION_PLAN: storyboard and execution differ")

    matching = [(b, e) for b, e in zip(board.scenes, supplied.scenes)
                if b.event_id == event_id and e.event_id == event_id]
    if not matching:
        raise RenderContractError(f"UNKNOWN_EVENT: {event_id!r}")

    board_scene, execution_scene = matching[0]
    if object_id not in execution_scene.visible_ids:
        raise RenderContractError(
            f"NOT_VISIBLE_BOARD_OBJECT: event={event_id!r} object={object_id!r}"
        )

    region_name = board_scene.object_regions.get(object_id)
    if region_name not in ("board", "scratch", "diagram") or region_name not in board_scene.regions:
        raise RenderContractError(
            f"INVALID_REGION: event={event_id!r} object={object_id!r}"
        )

    # A visible object can be restored in this scene; preserve its immutable
    # original LaTeX/provenance from any prior action, never synthesize content.
    defining = next((
        a for s in supplied.scenes for a in s.actions
        if a.object_id == object_id and a.kind == "progressive_write"
    ), None)
    if defining is None:
        raise RenderContractError(
            f"NO_ORIGINAL_FORMULA: event={event_id!r} object={object_id!r}"
        )
    return MathRenderRequest(
        event_id=event_id,
        object_id=object_id,
        latex=defining.latex,
        region=board_scene.regions[region_name],
        region_name=region_name,
        theme=board.theme,
        source_storyboard_sha256=supplied.source_storyboard_sha256,
        source_step_ids=tuple(defining.source_step_ids),
    )
