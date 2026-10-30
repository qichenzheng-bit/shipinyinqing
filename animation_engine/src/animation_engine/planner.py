"""Replay storyboard actions into checked, reproducible object-state snapshots.

This implementation validates *execution semantics*, never mathematical truth.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError
from visual_director.models import StoryboardPlan

from .models import ExecutionAction, ExecutionPlan, ExecutionScene


class ExecutionError(ValueError):
    """Structured storyboard/state contract violation."""


def _sha(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_execution_plan(storyboard: StoryboardPlan | dict[str, Any]) -> ExecutionPlan:
    """Compile a director storyboard to lifecycle transitions with no timing guesses."""
    try:
        board = StoryboardPlan.model_validate(storyboard)
    except (ValueError, ValidationError, TypeError) as exc:
        raise ExecutionError(f"STORYBOARD_SCHEMA: {str(exc)[:350]}") from exc
    if board.source_schema_version != "1.0":
        raise ExecutionError("STORYBOARD_SCHEMA: unsupported upstream schema")

    caption_ids = [cue.speech_unit_id for cue in board.captions]
    if len(caption_ids) != len(set(caption_ids)):
        raise ExecutionError("SPEECH_REFERENCE: duplicate caption anchors")
    known_speech = set(caption_ids)

    defined: dict[str, tuple[str, tuple[str, ...]]] = {}
    visible: list[str] = []
    archived: list[str] = []
    placement: dict[str, str] = {}
    all_action_ids: set[str] = set()
    all_event_ids: set[str] = set()
    output_scenes: list[ExecutionScene] = []

    for scene in board.scenes:
        eid = scene.event_id
        if not eid.strip() or eid in all_event_ids:
            raise ExecutionError(f"DUPLICATE_EVENT_ID: {eid!r}")
        all_event_ids.add(eid)
        if (len(set(scene.visible_ids)) != len(scene.visible_ids)
                or len(set(scene.archived_ids)) != len(scene.archived_ids)
                or set(scene.visible_ids) & set(scene.archived_ids)):
            raise ExecutionError(f"SNAPSHOT_MISMATCH: duplicate or conflicting object IDs in {eid}")
        if set(scene.object_regions) != set(scene.visible_ids):
            raise ExecutionError(f"SNAPSHOT_MISMATCH: object region keys disagree with visible IDs in {eid}")
        if any(region not in scene.regions for region in scene.object_regions.values()):
            raise ExecutionError(f"REGION_REFERENCE: missing region for visible object in {eid}")

        transitions: list[ExecutionAction] = []
        for action in scene.actions:
            aid, mid = action.action_id, action.object_id
            if not aid.strip() or aid in all_action_ids:
                raise ExecutionError(f"DUPLICATE_ACTION_ID: {aid!r} in {eid}")
            all_action_ids.add(aid)
            if not mid.strip() or action.event_id != eid:
                raise ExecutionError(f"ACTION_REFERENCE: {aid} belongs to wrong scene or object")
            if action.speech_unit_id not in known_speech:
                raise ExecutionError(f"SPEECH_REFERENCE: {eid}/{aid} -> {action.speech_unit_id!r}")
            if not action.latex.strip() or not action.source_step_ids:
                raise ExecutionError(f"OBJECT_PROVENANCE: {eid}/{aid} lacks LaTeX or source steps")

            signature = (action.latex, tuple(action.source_step_ids))
            if mid in defined and defined[mid] != signature:
                raise ExecutionError(f"OBJECT_ID_CONFLICT: {eid}/{mid} changes LaTeX or provenance")
            defined[mid] = signature

            before = "visible" if mid in visible else "archived" if mid in archived else "absent"
            from_region = placement.get(mid)
            target = scene.object_regions.get(
                mid, "scratch" if scene.layout == "split_scratch" else "board"
            )
            kind = action.kind
            to_region: str | None = None

            if kind == "progressive_write":
                if mid in visible:
                    raise ExecutionError(f"INVALID_TRANSITION: cannot rewrite visible object {eid}/{mid}")
                if mid in archived:
                    archived.remove(mid)
                visible.append(mid)
                placement[mid] = target
                to_region = target

            elif kind == "restore":
                if mid not in archived:
                    raise ExecutionError(f"INVALID_TRANSITION: restore requires archived object {eid}/{mid}")
                archived.remove(mid)
                visible.append(mid)
                placement[mid] = target
                to_region = target

            elif kind in ("retain", "group"):
                if mid not in visible:
                    raise ExecutionError(f"INVALID_TRANSITION: {kind} requires visible object {eid}/{mid}")
                placement[mid] = target
                to_region = target

            elif kind == "brief_highlight":
                if mid in visible:
                    to_region = placement[mid]
                elif (mid not in archived and action.source_action == "highlight"
                      and (scene.event_type == "read_question"
                           or action.latex.strip() in board.header.text)):
                    # The question is a pre-existing fixed header, not an
                    # additional, prematurely visible blackboard formula.
                    to_region = "question"
                else:
                    raise ExecutionError(f"INVALID_TRANSITION: highlight requires visible/header object {eid}/{mid}")

            elif kind == "archive":
                if mid not in visible:
                    raise ExecutionError(f"INVALID_TRANSITION: archive requires visible object {eid}/{mid}")
                visible.remove(mid)
                if mid not in archived:
                    archived.append(mid)
                placement.pop(mid, None)

            elif kind == "remove":
                if mid in visible:
                    visible.remove(mid)
                    placement.pop(mid, None)
                elif mid in archived:
                    archived.remove(mid)
                else:
                    raise ExecutionError(f"INVALID_TRANSITION: remove requires existing object {eid}/{mid}")

            else:
                raise ExecutionError(f"INVALID_TRANSITION: unsupported action {kind}")

            if to_region is not None and to_region not in scene.regions and to_region != "question":
                raise ExecutionError(f"REGION_REFERENCE: action {eid}/{aid} points outside scene")
            if to_region == "question" and "question" not in scene.regions:
                raise ExecutionError(f"REGION_REFERENCE: question missing from {eid}")

            after = "visible" if mid in visible else "archived" if mid in archived else "absent"
            transitions.append(ExecutionAction(
                action_id=aid, event_id=eid, object_id=mid,
                kind=kind, source_action=action.source_action,
                speech_unit_id=action.speech_unit_id, latex=action.latex,
                source_step_ids=list(action.source_step_ids),
                before=before, after=after,
                from_region=from_region, to_region=to_region,
            ))

        if (visible != scene.visible_ids or archived != scene.archived_ids
                or placement != scene.object_regions):
            raise ExecutionError(
                f"SNAPSHOT_MISMATCH: {eid}; expected visible={scene.visible_ids}, "
                f"archived={scene.archived_ids}, regions={scene.object_regions}; "
                f"computed visible={visible}, archived={archived}, regions={placement}"
            )
        state = {
            "visible_ids": visible,
            "archived_ids": archived,
            "regions": placement,
            "objects": {mid: {"latex": defined[mid][0], "source_step_ids": list(defined[mid][1])}
                        for mid in visible + archived},
        }
        output_scenes.append(ExecutionScene(
            event_id=eid, event_type=scene.event_type, layout=scene.layout,
            actions=transitions, visible_ids=list(visible),
            archived_ids=list(archived), object_regions=dict(placement),
            state_sha256=_sha(state),
        ))

    return ExecutionPlan(
        source_package_sha256=board.source_package_sha256,
        source_storyboard_sha256=_sha(board.model_dump(mode="json")),
        scenes=output_scenes,
    )
