"""Versioned, renderer-independent storyboard contract.

Teacher text and LaTeX are *never* re-derived here. Coordinates use normalized
screen or diagram-local coordinates, not pixels or animation seconds.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Rect(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)


class Theme(StrictModel):
    background: Literal["#FFFFFF"] = "#FFFFFF"
    ink: str = "#1E293B"
    highlight: str = "#2563EB"
    secondary_highlight: str = "#EA580C"
    caption_ink: str = "#1E293B"
    boxed_answer: Literal[False] = False


class HeaderPlan(StrictModel):
    text: str
    align: Literal["center", "left"]
    position: Literal["top_fixed"] = "top_fixed"
    lines: int = Field(ge=1)
    height: float = Field(gt=0, le=.38)
    font_scale: float = Field(gt=0)
    overflow: bool = False


class DiagramPoint(StrictModel):
    id: str = Field(min_length=1)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    label: str = ""  # mathematical labels are LaTeX source, not TTS phonetics


class DiagramLine(StrictModel):
    id: str = Field(min_length=1)
    start: str
    end: str
    dashed: bool = False


class DiagramCurve(StrictModel):
    id: str = Field(min_length=1)
    points: list[tuple[float, float]]  # explicit samples; NEVER inferred from question text


class DiagramSpec(StrictModel):
    event_id: str
    points: list[DiagramPoint] = Field(default_factory=list)
    lines: list[DiagramLine] = Field(default_factory=list)
    curves: list[DiagramCurve] = Field(default_factory=list)


class LabelPlacement(StrictModel):
    point_id: str
    text_latex: str
    x: float  # label rectangle top-left in diagram-local coordinates
    y: float
    w: float
    h: float


class DiagramPlacement(StrictModel):
    points: list[DiagramPoint]
    lines: list[DiagramLine]
    curves: list[DiagramCurve]
    labels: list[LabelPlacement]


class DirectorOptions(StrictModel):
    allow_needs_review: bool = False
    max_visible_formulas: int = Field(default=6, ge=2, le=100)
    diagrams: list[DiagramSpec] = Field(default_factory=list)


class CaptionPart(StrictModel):
    kind: Literal["text", "math"]
    value: str


class CaptionCue(StrictModel):
    subtitle_id: str
    speech_unit_id: str
    parts: list[CaptionPart]
    start_second: None = None  # assigned only by the downstream actual-audio aligner
    end_second: None = None


class BoardVisualAction(StrictModel):
    action_id: str
    event_id: str
    object_id: str
    latex: str
    kind: Literal[
        "progressive_write", "brief_highlight", "retain", "group",
        "remove", "archive", "restore"
    ]
    source_action: str
    speech_unit_id: str
    anchor: Literal["speech_unit"] = "speech_unit"
    reason: str
    color_restore: bool = True
    source_step_ids: list[str]  # provenance preserved


class ScenePlan(StrictModel):
    event_id: str
    event_type: str
    layout: Literal["full_board", "split_scratch", "matrix_compare", "proof_scroll", "diagram_split"]
    regions: dict[str, Rect]
    actions: list[BoardVisualAction]
    visible_ids: list[str]
    archived_ids: list[str]
    object_regions: dict[str, Literal["board", "scratch", "diagram"]]
    scroll_board: bool
    diagram: DiagramPlacement | None = None


class StoryboardPlan(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    source_input_sha256: str
    source_package_sha256: str  # all frozen teacher content, not just user input
    source_schema_version: str
    theme: Theme
    header: HeaderPlan
    scenes: list[ScenePlan]
    captions: list[CaptionCue]
    warnings: list[str]
    renderer: Literal["not_implemented"] = "not_implemented"
    timing: Literal["semantic_anchors_only"] = "semantic_anchors_only"