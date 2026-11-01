"""2.2 storyboard-bound, explicitly approved mathematical animation cues."""
import copy
import json
from pathlib import Path

import pytest
from visual_director import build_storyboard
from animation_engine import build_execution_plan
from animation_engine.writing_cues import MathWritingError, plan_math_writing

PACKAGE = Path(__file__).resolve().parents[2] / "visual_director" / "tests" / "fixtures" / "limit_teaching_package.json"


@pytest.fixture
def inputs():
    board = build_storyboard(json.loads(PACKAGE.read_text(encoding="utf-8")))
    execution = build_execution_plan(board)
    hint = {
        "source_storyboard_sha256": execution.source_storyboard_sha256,
        "event_id": "e_k_sin", "object_id": "m_k_sin",
        "action_id": "b_k_sin", "speech_unit_id": "u_k_sin",
        "parts": [r"\sin x", "=x-", r"\frac{x^3}{6}", "+o(x^3)"],
        "highlight_index": 2,
    }
    return board, execution, hint


def test_valid_structural_parts_preserve_source_contract_and_originals(inputs):
    board, execution, hint = inputs
    original = (board.model_dump_json(), execution.model_dump_json(), copy.deepcopy(hint))
    plan = plan_math_writing(board, execution, event_id="e_k_sin",
                             object_id="m_k_sin", hint=hint)
    assert plan.mode == "segmented"
    assert plan.hint_source == "approved_explicit"
    assert plan.parts == tuple(hint["parts"])
    assert "".join(plan.parts) == r"\sin x=x-\frac{x^3}{6}+o(x^3)"
    assert plan.highlight_index == 2
    assert plan.action_id == "b_k_sin" and plan.speech_unit_id == "u_k_sin"
    assert plan.request.latex == "".join(plan.parts)
    assert plan.request.source_step_ids == ("s5a", "s5")
    assert (board.model_dump_json(), execution.model_dump_json(), hint) == original


def test_no_hint_falls_back_to_single_whole_formula_write_and_highlight(inputs):
    board, execution, _ = inputs
    p = plan_math_writing(board, execution, event_id="e_k_sin", object_id="m_k_sin")
    assert p.mode == "whole_formula" and p.hint_source == "safe_fallback"
    assert p.parts == (p.request.latex,)
    assert p.highlight_index == 0


@pytest.mark.parametrize("field,value,match", [
    ("source_storyboard_sha256", "0"*64, "HINT_PROVENANCE"),
    ("event_id", "e_wrong", "HINT_PROVENANCE"),
    ("object_id", "m_wrong", "HINT_PROVENANCE"),
    ("action_id", "b_wrong", "HINT_PROVENANCE"),
    ("speech_unit_id", "u_wrong", "HINT_PROVENANCE"),
    ("parts", [r"\sin x", "=x-", r"\frac{x^3}{7}", "+o(x^3)"], "HINT_LATEX_MISMATCH"),
    ("parts", [r"\sin x", "=x-"], "HINT_LATEX_MISMATCH"),
    ("highlight_index", 4, "HINT_HIGHLIGHT_INDEX"),
    ("highlight_index", -1, "HINT_HIGHLIGHT_INDEX"),
    ("highlight_index", "2", "HINT_HIGHLIGHT_INDEX"),
])
def test_untrusted_or_wrong_hint_fails_instead_of_silent_fallback(inputs, field, value, match):
    board, execution, hint = inputs
    hint[field] = value
    with pytest.raises(MathWritingError, match=match):
        plan_math_writing(board, execution, event_id="e_k_sin",
                          object_id="m_k_sin", hint=hint)


def test_reject_unknown_hint_fields_and_unsafe_math(inputs):
    board, execution, hint = inputs
    hint["source_override"] = "x=999"
    with pytest.raises(MathWritingError, match="HINT_SCHEMA"):
        plan_math_writing(board, execution, event_id="e_k_sin",
                          object_id="m_k_sin", hint=hint)


def test_reject_wrong_original_execution_even_with_plausible_hint(inputs):
    board, execution, hint = inputs
    execution.scenes[0].state_sha256 = "1"*64
    with pytest.raises(MathWritingError, match="MISMATCH_EXECUTION_PLAN"):
        plan_math_writing(board, execution, event_id="e_k_sin", object_id="m_k_sin", hint=hint)


def test_reject_header_question_as_written_formula(inputs):
    board, execution, _ = inputs
    with pytest.raises(MathWritingError, match="NOT_VISIBLE_BOARD_OBJECT"):
        plan_math_writing(board, execution, event_id="e_read", object_id="m_read")


def test_missing_speech_association_does_not_invent_narration(inputs):
    board, execution, hint = inputs
    assert hint["speech_unit_id"] == "u_k_sin"
    p = plan_math_writing(board, execution, event_id="e_k_sin", object_id="m_k_sin", hint=hint)
    assert not hasattr(p, "speech_start_second") and not hasattr(p, "speech_end_second")
