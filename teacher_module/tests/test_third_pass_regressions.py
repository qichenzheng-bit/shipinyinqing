"""Third review: sourced board formula and safe symbolic budget."""
import ast

import pytest
from math_teacher.models import MathCheckRequest
from math_teacher.validator import Collector, check_lesson
from math_teacher.verifier import verify_math_check


def _codes(report):
    return {issue.code for issue in report.issues}


def test_unrelated_spoken_equation_is_not_a_trusted_source(understanding, plan, draft):
    # The model puts the SAME fabricated equality in speech and on the board.
    # Matching its own words is not an independent mathematical source.
    draft.math_objects[0].latex = "x=999"
    draft.speech_units[0].parts[1].value = "x=999"
    report = Collector()
    check_lesson(understanding, plan, draft, report)
    assert "BOARD_SPEECH_ONLY_MATH" in _codes(report)
    assert any(issue.severity == "review" and issue.code == "BOARD_SPEECH_ONLY_MATH"
               for issue in report.issues)


def test_source_anchored_equation_does_not_need_extra_board_review(understanding, plan, draft):
    understanding.solution_steps[0].input_expressions.append("x^2")
    report = Collector()
    check_lesson(understanding, plan, draft, report)
    assert "BOARD_SPEECH_ONLY_MATH" not in _codes(report)


def test_nested_power_is_rejected_before_sympy_evaluates_it():
    from math_teacher.verifier import _validate_power_budget

    expression = "100000" + "**8" * 9
    assert len(expression) < 240
    with pytest.raises(ValueError, match="power|budget|complexity|integer"):
        _validate_power_budget(ast.parse(expression, mode="eval"))


def test_normal_polynomial_identity_still_verifies():
    req = MathCheckRequest(check_id="polynomial", step_id="s1",
                           kind="algebraic_identity",
                           lhs_expr="(x-1)*(x+1)", rhs_expr="x**2-1",
                           conditions=[])
    assert verify_math_check(req).status == "verified"
