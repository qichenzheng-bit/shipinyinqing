"""Immutable-by-contract output of the deterministic step-1 animation planner.

This module describes object lifecycle and ordering only: no seconds, Manim,
animation frames, new mathematical content, or invented speech.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ObjectState = Literal["absent", "visible", "archived"]
RegionName = Literal["board", "scratch", "diagram", "question"]
ActionKind = Literal[
    "progressive_write", "brief_highlight", "retain", "group",
    "remove", "archive", "restore",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ExecutionAction(StrictModel):
    action_id: str
    event_id: str
    object_id: str
    kind: ActionKind
    source_action: str
    speech_unit_id: str
    latex: str
    source_step_ids: list[str] = Field(min_length=1)
    before: ObjectState
    after: ObjectState
    from_region: RegionName | None
    to_region: RegionName | None


class ExecutionScene(StrictModel):
    event_id: str
    event_type: str
    layout: str
    actions: list[ExecutionAction]
    visible_ids: list[str]
    archived_ids: list[str]
    object_regions: dict[str, Literal["board", "scratch", "diagram"]]
    state_sha256: str


class ExecutionPlan(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source_package_sha256: str
    source_storyboard_sha256: str
    sync_status: Literal["semantic_anchors_only"] = "semantic_anchors_only"
    scenes: list[ExecutionScene]
