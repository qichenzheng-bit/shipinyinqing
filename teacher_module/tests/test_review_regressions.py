"""Regression cases from V1 cross-module review (no external model required)."""
from math_teacher.models import MathCheckRequest, SourceSegment
from math_teacher.validator import Collector, check_understanding, check_plan, check_lesson


def _codes(collector):
    return {item.code for item in collector.issues}


def test_unrelated_true_identity_cannot_verify_derived_step(source, understanding):
    step = understanding.solution_steps[0].model_copy(deep=True)
    step.step_id = "s2"
    step.origin = "derived"
    step.depends_on = ["s1"]
    step.input_expressions = ["x**2-1"]
    step.output_expressions = ["(x-1)*(x+1)"]
    understanding.solution_steps.append(step)
    understanding.check_requests = [MathCheckRequest(
        check_id="u", step_id="s2", kind="algebraic_identity",
        lhs_expr="(y+1)**2", rhs_expr="y**2+2*y+1", conditions=[],
    )]
    c = Collector()
    check_understanding(source.with_sources(), understanding, c)
    assert "MATH_CHECK_UNBOUND" in _codes(c)
    assert "ADDED_STEP_REQUIRES_REVIEW" in _codes(c)


def test_check_matching_step_expressions_can_verify_polynomial(source, understanding):
    step = understanding.solution_steps[0].model_copy(deep=True)
    step.step_id = "s2"
    step.origin = "derived"
    step.depends_on = ["s1"]
    step.input_expressions = ["x**2-1"]
    step.output_expressions = ["(x-1)*(x+1)"]
    understanding.solution_steps.append(step)
    understanding.check_requests = [MathCheckRequest(
        check_id="valid", step_id="s2", kind="algebraic_identity",
        lhs_expr="x**2-1", rhs_expr="(x-1)*(x+1)", conditions=[],
    )]
    c = Collector()
    check_understanding(source.with_sources(), understanding, c)
    assert "MATH_CHECK_UNBOUND" not in _codes(c)
    assert "ADDED_STEP_REQUIRES_REVIEW" not in _codes(c)


def test_backward_source_segment_reference_rejected(source, understanding):
    source.reference_solution = "先化简。再求极限。"
    source.solution_segments = [
        SourceSegment(source_id="solution:0", text="先化简。", kind="solution"),
        SourceSegment(source_id="solution:1", text="再求极限。", kind="solution"),
    ]
    first = understanding.solution_steps[0]
    first.source_refs = ["solution:1"]
    second = first.model_copy(deep=True)
    second.step_id = "s2"
    second.source_refs = ["solution:0"]
    second.depends_on = ["s1"]
    understanding.solution_steps.append(second)
    c = Collector()
    check_understanding(source, understanding, c)
    assert "SOURCE_STEP_ORDER" in _codes(c)


def test_organizational_step_cannot_assert_unverified_math(source, understanding):
    step = understanding.solution_steps[0].model_copy(deep=True)
    step.step_id = "notation"
    step.origin = "organizational"
    step.depends_on = ["s1"]
    step.input_expressions = ["x"]
    step.output_expressions = ["x=17"]
    step.relation_type = "equals"
    understanding.solution_steps.append(step)
    c = Collector()
    check_understanding(source.with_sources(), understanding, c)
    assert "ORGANIZATIONAL_ASSERTION_REQUIRES_REVIEW" in _codes(c)


def test_board_object_must_belong_to_event_source_step(understanding, plan, draft):
    step = understanding.solution_steps[0].model_copy(deep=True)
    step.step_id = "s2"
    understanding.solution_steps.append(step)
    draft.math_objects[0].source_step_ids = ["s2"]
    c = Collector()
    check_lesson(understanding, plan, draft, c)
    assert "BOARD_STEP_CONTEXT_MISMATCH" in _codes(c)


def test_speech_units_follow_event_and_unit_order(understanding, plan, draft):
    draft.speech_units[0], draft.speech_units[1] = draft.speech_units[1], draft.speech_units[0]
    c = Collector()
    check_lesson(understanding, plan, draft, c)
    assert "SPEECH_ORDER_MISMATCH" in _codes(c)


def test_duplicate_speech_membership_rejected(understanding, plan, draft):
    draft.lesson_events[0].speech_unit_ids.append(draft.lesson_events[0].speech_unit_ids[0])
    c = Collector()
    check_lesson(understanding, plan, draft, c)
    assert "DUPLICATE_EVENT_MEMBER" in _codes(c)


def test_knowledge_must_precede_first_relevant_derivation(understanding, plan):
    early = plan.teaching_events[3].model_copy(deep=True)
    early.event_id = "early"
    plan.teaching_events.insert(1, early)
    plan.reference_step_coverage["s1"].insert(1, "early")
    c = Collector()
    check_plan(understanding, plan, c)
    assert "INVALID_KNOWLEDGE_SEQUENCE" in _codes(c)


def test_source_step_requires_exact_quote_from_reference(source, understanding):
    c = Collector()
    check_understanding(source.with_sources(), understanding, c)
    assert "SOURCE_QUOTE_REQUIRED" in _codes(c)


def test_quote_order_within_one_source_segment_is_checked(source, understanding):
    source.reference_solution = "先处理分母，随后化简分子，最后计算极限。"
    first = understanding.solution_steps[0]
    first.source_quotes = {"solution:0": "最后计算极限"}
    second = first.model_copy(deep=True)
    second.step_id = "s2"
    second.source_quotes = {"solution:0": "先处理分母"}
    second.depends_on = ["s1"]
    understanding.solution_steps.append(second)
    c = Collector()
    check_understanding(source.with_sources(), understanding, c)
    assert "SOURCE_STEP_ORDER" in _codes(c)


def test_quote_must_be_substring_of_real_source(source, understanding):
    understanding.solution_steps[0].source_quotes = {"solution:0": "这是不存在于参考解析的句子"}
    c = Collector()
    check_understanding(source.with_sources(), understanding, c)
    assert "SOURCE_QUOTE_MISMATCH" in _codes(c)
