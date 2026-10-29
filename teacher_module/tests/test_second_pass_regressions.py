"""Focused second-pass regression tests: only previously reported defects."""
import json
from math_teacher.models import MathCheckRequest, SourceSegment
from math_teacher.validator import Collector, check_understanding, check_lesson
from math_teacher.verifier import verify_math_check


def _codes(collector):
    return {issue.code for issue in collector.issues}


def test_true_algebra_does_not_verify_limit_reasoning(source, understanding):
    step = understanding.solution_steps[0].model_copy(deep=True)
    step.step_id = "derived_limit"
    step.origin = "derived"
    step.depends_on = ["s1"]
    step.input_expressions = ["x**2-1"]
    step.output_expressions = ["(x-1)*(x+1)"]
    step.relation_type = "limit"
    understanding.solution_steps.append(step)
    understanding.check_requests = [MathCheckRequest(
        check_id="c", step_id="derived_limit", kind="algebraic_identity",
        lhs_expr="x**2-1", rhs_expr="(x-1)*(x+1)", conditions=[])]
    collector = Collector()
    check_understanding(source.with_sources(), understanding, collector)
    assert "ADDED_STEP_REQUIRES_REVIEW" in _codes(collector)


def test_math_checker_does_not_claim_sqrt_negative_real_identity():
    outcome = verify_math_check(MathCheckRequest(
        check_id="c", step_id="s", kind="algebraic_identity",
        lhs_expr="sqrt(-1)**2", rhs_expr="-1", conditions=[]))
    assert outcome.status == "undetermined"


def test_same_quote_may_identify_second_distinct_occurrence(source, understanding):
    source.reference_solution = "先化简，然后检查，再化简，最后求极限。"
    first = understanding.solution_steps[0]
    first.source_quotes = {"solution:0": "化简"}
    second = first.model_copy(deep=True)
    second.step_id = "s2"
    second.depends_on = ["s1"]
    second.source_quotes = {"solution:0": "化简"}
    understanding.solution_steps.append(second)
    collector = Collector()
    check_understanding(source.with_sources(), understanding, collector)
    assert "SOURCE_STEP_ORDER" not in _codes(collector)


def test_math_identity_accepts_simple_latex_exponent_notation(source, understanding):
    step = understanding.solution_steps[0].model_copy(deep=True)
    step.step_id = "s2"
    step.origin = "derived"
    step.depends_on = ["s1"]
    step.relation_type = "equals"
    step.input_expressions = ["x^{2}-1"]
    step.output_expressions = ["(x-1)(x+1)"]
    understanding.solution_steps.append(step)
    understanding.check_requests = [MathCheckRequest(
        check_id="c", step_id="s2", kind="algebraic_identity",
        lhs_expr="x**2-1", rhs_expr="(x-1)*(x+1)", conditions=[])]
    collector = Collector()
    check_understanding(source.with_sources(), understanding, collector)
    assert "MATH_CHECK_UNBOUND" not in _codes(collector)
    assert "ADDED_STEP_REQUIRES_REVIEW" not in _codes(collector)


def test_non_matching_question_opening_is_flagged(source, understanding, plan, draft):
    from math_teacher.models import SpeechPart
    draft.speech_units[0].parts = [SpeechPart(kind="text",value="接下来讲几个步骤。",reading_intent=None)]
    collector = Collector()
    check_lesson(understanding,plan,draft,collector,source=source.with_sources())
    assert "READ_QUESTION_ANCHOR_WEAK" in _codes(collector)


def test_organizational_other_math_assertion_requires_review(source, understanding):
    step = understanding.solution_steps[0].model_copy(deep=True)
    step.step_id = "s2"
    step.origin = "organizational"
    step.depends_on = ["s1"]
    step.relation_type = "other"
    step.output_expressions = ["x=17"]
    understanding.solution_steps.append(step)
    collector = Collector()
    check_understanding(source.with_sources(),understanding,collector)
    assert "ORGANIZATIONAL_ASSERTION_REQUIRES_REVIEW" in _codes(collector)
