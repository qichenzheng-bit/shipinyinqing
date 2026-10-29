"""Regression tests for strict knowledge, board relevance and source integrity."""
import pytest

from math_teacher.models import SourceSegment
from math_teacher.pipeline import MathTeacherPipeline, PipelineValidationError
from conftest import FakeProvider


def assert_rejected(source, understanding, plan, draft, stage, code, **options):
    provider = FakeProvider(understanding, plan, draft)
    with pytest.raises(PipelineValidationError) as error:
        MathTeacherPipeline(provider).run(source, **options)
    assert error.value.stage == stage
    assert any(issue.code == code for issue in error.value.report.issues)
    return provider


def test_reject_knowledge_without_applicability_conditions(source, understanding, plan, draft):
    plan.knowledge_bindings[0].applicability_conditions = []
    assert_rejected(source, understanding, plan, draft, "B", "KNOWLEDGE_MISSING_CONDITIONS", allow_needs_review=True)


def test_reject_knowledge_without_problem_mapping(source, understanding, plan, draft):
    plan.knowledge_bindings[0].application_mapping = {}
    assert_rejected(source, understanding, plan, draft, "B", "KNOWLEDGE_MISSING_APPLICATION", allow_needs_review=True)


def test_reject_placeholder_knowledge_conditions_or_mapping(source, understanding, plan, draft):
    plan.knowledge_bindings[0].applicability_conditions = ["  "]
    plan.knowledge_bindings[0].application_mapping = {"u": " "}
    provider = FakeProvider(understanding, plan, draft)
    with pytest.raises(PipelineValidationError) as error:
        MathTeacherPipeline(provider).run(source)
    codes = {issue.code for issue in error.value.report.issues}
    assert {"KNOWLEDGE_MISSING_CONDITIONS", "KNOWLEDGE_MISSING_APPLICATION"} <= codes


def test_reject_unrelated_board_formula(source, understanding, plan, draft):
    draft.math_objects[0].latex = "y^3"  # Not spoken, justified, or supplied in source.
    assert_rejected(source, understanding, plan, draft, "C", "BOARD_UNRELATED_TO_CONTEXT")


def test_allow_unspoken_board_formula_from_reference_step(source, understanding, plan, draft):
    # A formula may appear only on the board if it has an explicit reference-step source.
    understanding.solution_steps[0].input_expressions.append("z^3")
    draft.math_objects[0].latex = "z^3"
    result = MathTeacherPipeline(FakeProvider(understanding, plan, draft)).run(source)
    assert result.validation.status == "ready_with_limits"


def test_reject_segment_text_that_is_not_in_original_solution(source, understanding, plan, draft):
    source.solution_segments = [SourceSegment(source_id="solution:0", kind="solution", text="用洛必达法则得到 1/2。")]
    provider = assert_rejected(source, understanding, plan, draft, "input", "SOURCE_TEXT_MISMATCH")
    assert provider.calls == []  # Reject before sending a false source to an LLM.


def test_reject_segment_omission_even_when_all_segment_ids_are_covered(source, understanding, plan, draft):
    source.reference_solution = "使用泰勒展开，先化简分子，然后求得极限 1/2。"
    source.solution_segments = [SourceSegment(source_id="solution:0", kind="solution", text="使用泰勒展开，")]
    assert_rejected(source, understanding, plan, draft, "input", "SOURCE_TEXT_MISMATCH")


def test_accept_ordered_segments_with_whitespace_gaps(source, understanding, plan, draft):
    source.reference_solution = "使用泰勒展开  求得极限 1/2。"
    source.solution_segments = [
        SourceSegment(source_id="solution:0", kind="solution", text="使用泰勒展开"),
        SourceSegment(source_id="solution:1", kind="solution", text="求得极限 1/2。"),
    ]
    understanding.solution_steps[0].source_refs = ["solution:0", "solution:1"]
    result = MathTeacherPipeline(FakeProvider(understanding, plan, draft)).run(source)
    assert result.validation.status == "ready_with_limits"
