"""Validate explicit mathematical part boundaries without inferring mathematical content.

This is a pure semantic planning layer: no Manim, no clock times, no TTS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from visual_director.models import StoryboardPlan
from .models import ExecutionPlan
from .mathtex_renderer import MathTexRenderError, validate_math_latex
from .render_contract import MathRenderRequest, RenderContractError, select_math_render_request


class MathWritingError(ValueError):
    """The mathematical writing preview cannot honor the requested hint."""


@dataclass(frozen=True)
class MathWritingPlan:
    request: MathRenderRequest
    action_id: str
    speech_unit_id: str
    parts: tuple[str, ...]
    highlight_index: int | None
    mode: Literal["segmented", "whole_formula"]
    hint_source: Literal["approved_explicit", "safe_fallback"]


_HINT_FIELDS = frozenset({
    "source_storyboard_sha256", "event_id", "object_id", "action_id",
    "speech_unit_id", "parts", "highlight_index",
})


def plan_math_writing(
    storyboard: StoryboardPlan | dict[str, Any],
    execution: ExecutionPlan | dict[str, Any],
    *,
    event_id: str,
    object_id: str,
    hint: dict[str, Any] | None = None,
) -> MathWritingPlan:
    try:
        req = select_math_render_request(
            storyboard, execution, event_id=event_id, object_id=object_id
        )
        plan = ExecutionPlan.model_validate(execution)
    except (RenderContractError, ValueError, TypeError) as exc:
        raise MathWritingError(str(exc)) from exc

    # Only already-created objects are eligible. Reusing the same visual
    # formula at a later lesson event never changes its original write ID.
    defining = None
    for scene in plan.scenes:
        for action in scene.actions:
            if action.object_id == object_id and action.kind == "progressive_write":
                defining = action
                break
        if scene.event_id == event_id:
            break
    if defining is None:
        raise MathWritingError(f"NO_ORIGINAL_WRITE: {event_id}/{object_id}")

    if hint is None:
        return MathWritingPlan(
            request=req, action_id=defining.action_id,
            speech_unit_id=defining.speech_unit_id,
            parts=(req.latex,), highlight_index=0,
            mode="whole_formula", hint_source="safe_fallback",
        )

    if not isinstance(hint, dict) or set(hint) != _HINT_FIELDS:
        raise MathWritingError("HINT_SCHEMA: exact supported fields are required")
    for field, expected in (
        ("source_storyboard_sha256", req.source_storyboard_sha256),
        ("event_id", event_id),
        ("object_id", object_id),
        ("action_id", defining.action_id),
        ("speech_unit_id", defining.speech_unit_id),
    ):
        if type(hint[field]) is not str or hint[field] != expected:
            raise MathWritingError(f"HINT_PROVENANCE: {field} does not match approved execution")

    parts = hint["parts"]
    if (type(parts) is not list or len(parts) < 2
            or any(type(p) is not str or not p for p in parts)):
        raise MathWritingError("HINT_SCHEMA: parts must be two or more nonempty strings")
    if "".join(parts) != req.latex:
        raise MathWritingError("HINT_LATEX_MISMATCH: math parts must concatenate exactly to source")

    index = hint["highlight_index"]
    if index is not None and (type(index) is not int or not (0 <= index < len(parts))):
        raise MathWritingError("HINT_HIGHLIGHT_INDEX: occurrence index is out of range")

    # Catch unsafe/incomplete fragment commands before any external TeX
    # process; explicit parts aren't automatically 'trusted' just because
    # their concatenation is the original mathematical formula.
    for i, part in enumerate(parts):
        try:
            validate_math_latex(part)
        except MathTexRenderError as exc:
            raise MathWritingError(f"HINT_PART_INVALID: {i}: {exc}") from exc

    return MathWritingPlan(
        request=req, action_id=defining.action_id,
        speech_unit_id=defining.speech_unit_id,
        parts=tuple(parts), highlight_index=index,
        mode="segmented", hint_source="approved_explicit",
    )
