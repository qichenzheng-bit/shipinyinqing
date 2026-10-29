"""Versioned contracts shared by three AI stages and the deterministic compiler.

Raw material is always preserved. Mathematical judgments from an LLM are
candidates; only validators may record independently verified facts.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceSegment(StrictModel):
    source_id: str
    text: str
    kind: Literal["problem", "solution"]


class TeacherInput(StrictModel):
    problem: str = Field(min_length=1)
    reference_solution: str = Field(min_length=1)
    # Source segments represent the input module's validated transcription.
    # Empty means the entire original field is a single source segment.
    problem_segments: list[SourceSegment] = Field(default_factory=list)
    solution_segments: list[SourceSegment] = Field(default_factory=list)

    def with_sources(self) -> "TeacherInput":
        return self.model_copy(update={
            "problem_segments": self.problem_segments or [SourceSegment(source_id="problem:0", text=self.problem, kind="problem")],
            "solution_segments": self.solution_segments or [SourceSegment(source_id="solution:0", text=self.reference_solution, kind="solution")],
        })


class MathStep(StrictModel):
    step_id: str
    origin: Literal["source", "derived", "organizational"]
    source_refs: list[str]
    # Literal quotations from each referenced solution segment; source steps
    # use them to validate within-segment order, not just segment ID order.
    source_quotes: dict[str, str] = Field(default_factory=dict)
    step_role: str
    input_expressions: list[str]
    output_expressions: list[str]
    relation_type: Literal["equals", "asymptotic", "limit", "implies", "iff", "definition", "other"]
    operation: str
    depends_on: list[str]
    assumptions: list[str]
    justification: str
    verification_status: Literal["pending_check", "source_only"]


class ProblemUnderstanding(StrictModel):
    domain: str
    problem_type: str
    goal: str
    conditions: list[str]
    math_objects: list[str]
    subquestions: list[str]


class MathCheckRequest(StrictModel):
    check_id: str
    step_id: str
    kind: Literal["algebraic_identity"]
    lhs_expr: str
    rhs_expr: str
    conditions: list[str]


class AnalysisIssue(StrictModel):
    code: str
    description: str
    source_refs: list[str]
    critical: bool


class Understanding(StrictModel):
    problem_understanding: ProblemUnderstanding
    reference_method: str
    solution_structure: str
    solution_steps: list[MathStep]
    check_requests: list[MathCheckRequest]
    issues: list[AnalysisIssue]
    review_status: Literal["ready_candidate", "needs_confirmation", "blocked"]


class KnowledgeBinding(StrictModel):
    knowledge_id: str
    source_step_ids: list[str]
    knowledge_type: Literal["formula", "theorem", "definition", "method"]
    title: str
    formula_or_theorem: str
    applicability_conditions: list[str]
    application_mapping: dict[str, str]
    teaching_reason: str
    return_to_step_id: str


class PlannedEvent(StrictModel):
    event_id: str
    event_type: Literal[
        "read_question", "orient", "knowledge", "application", "derivation",
        "proof", "branch", "subgoal", "conclusion"
    ]
    source_step_ids: list[str]
    knowledge_binding_ids: list[str]
    teaching_goal: str
    intended_board_content: list[str]
    mathematical_progression: str


class SupplementRequest(StrictModel):
    source_step_ids: list[str]
    reason: str
    suggested_mathematical_step: str


class TeachingPlan(StrictModel):
    teaching_strategy: str
    reference_step_coverage: dict[str, list[str]]
    knowledge_bindings: list[KnowledgeBinding]
    teaching_events: list[PlannedEvent]
    supplement_requests: list[SupplementRequest]
    planning_issues: list[str]


class SpeechPart(StrictModel):
    kind: Literal["text", "math"]
    value: str
    reading_intent: str | None


class SpeechUnit(StrictModel):
    speech_unit_id: str
    event_id: str
    parts: list[SpeechPart]


class MathObject(StrictModel):
    math_object_id: str
    latex: str
    source_step_ids: list[str]


class BoardAction(StrictModel):
    board_action_id: str
    event_id: str
    speech_unit_id: str
    math_object_id: str
    action: Literal["write", "transform", "substitute", "highlight", "group", "retain", "remove"]
    semantic_reason: str


class AnimationIntent(StrictModel):
    animation_id: str
    event_id: str
    speech_unit_ids: list[str]
    board_action_ids: list[str]
    mathematical_goal: str


class LessonEvent(StrictModel):
    event_id: str
    source_step_ids: list[str]
    knowledge_binding_ids: list[str]
    speech_unit_ids: list[str]
    board_action_ids: list[str]
    animation_intent_ids: list[str]


class LessonDraft(StrictModel):
    lesson_events: list[LessonEvent]
    speech_units: list[SpeechUnit]
    math_objects: list[MathObject]
    board_actions: list[BoardAction]
    animation_intents: list[AnimationIntent]
    consistency_issues: list[str]


class SubtitleCandidate(StrictModel):
    subtitle_id: str
    speech_unit_id: str
    parts: list[SpeechPart]  # deterministic projection; cannot independently invent content


class ValidationIssue(StrictModel):
    stage: str
    code: str
    severity: Literal["error", "review", "warning"]
    detail: str


class MathVerification(StrictModel):
    check_id: str
    step_id: str
    status: Literal["verified", "failed", "undetermined"]
    explanation: str


class ValidationReport(StrictModel):
    issues: list[ValidationIssue]
    math_checks: list[MathVerification]
    status: Literal["blocked", "needs_review", "ready_with_limits"]


class TeachingPackage(StrictModel):
    schema_version: Literal["1.0"]
    input_sha256: str
    prompt_versions: dict[str, str]
    source: TeacherInput
    understanding: Understanding
    plan: TeachingPlan
    lesson: LessonDraft
    subtitles: list[SubtitleCandidate]
    validation: ValidationReport
