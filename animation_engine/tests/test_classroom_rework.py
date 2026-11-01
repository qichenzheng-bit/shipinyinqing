"""Classroom-led redesign contract tests: not visual proof by themselves."""
import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent/'fixtures'))
from animation_engine.classroom_cues import (checked_cues, BOARD_TEXT_STYLE,
    BOARD_DETAIL_FONT_PX, BOARD_DERIVATION_INK, BOARD_GUIDANCE_PHASES)
from animation_engine.board_motion import interpolated_collisions, math_placement_collisions
from animation_engine.longboard_plan import LongboardError, build_longboard_plan, GlyphSize
from build_classroom_rework_example import build


def sample():
    _, board, execution, cues, policy = build()
    return board, execution, cues, policy


def test_new_teacher_source_has_exact_full_event_coverage():
    board, plan, cues, policy = sample()
    out = checked_cues(cues, board, plan)
    assert len(out) == 14
    assert [c["event_id"] for c in out] == [s.event_id for s in board.scenes]
    assert all(c["source_step_ids"] for c in out)
    assert cues["source_storyboard_sha256"] == plan.source_storyboard_sha256


def test_no_undocumented_teaching_wording_or_math_in_cjk_layer():
    board, plan, cues, policy = sample()
    changed=copy.deepcopy(cues)
    changed["events"][2]["detail"]="由 x 的值计算"
    with pytest.raises(LongboardError,match="PURE_TEXT"):
        checked_cues(changed,board,plan)
    changed=copy.deepcopy(cues)
    changed["events"][0]["source_step_ids"]=["unproven"]
    with pytest.raises(LongboardError,match="PROVENANCE"):
        checked_cues(changed,board,plan)


def test_cues_strict_hash_and_order_fail_closed():
    board, plan, cues, policy = sample()
    changed=copy.deepcopy(cues)
    changed["source_storyboard_sha256"]="0"*64
    with pytest.raises(LongboardError,match="SOURCE_HASH"):
        checked_cues(changed,board,plan)
    changed=copy.deepcopy(cues)
    changed["events"][1]["event_id"]="e_read"
    with pytest.raises(LongboardError,match="ORDER"):
        checked_cues(changed,board,plan)


def test_compact_whole_board_centered_and_clean_without_forced_cuts():
    board, plan, cues, policy = sample()
    assert policy["board_mode"] == "simple_full_board"
    assert policy["cut_before_events"] == []
    result = build_longboard_plan(
        board, plan, policy=policy,
        measure=lambda latex, height: GlyphSize(195, 46)
    )
    assert len(result["events"]) == 14
    assert result["events"][-1]["new_ids"] == ["m_final"]
    assert result["policy"]["content_top_offset_px"] == 0
    assert result["policy"]["guidance_style"] == "board_context"
    assert result["policy"]["math_base_scale"] == .5625
    by_event={x["event_id"]:x for x in result["events"]}
    # Write the completed J result as the last mathematical step first;
    # only the following event may move it into retained context.
    assert "m_jresult" in by_event["e_jresult"]["new_ids"]
    assert "m_jresult" in by_event["e_jresult"]["active_ids"]
    assert "m_jresult" not in by_event["e_jresult"]["fixed_ids"]
    assert "m_jresult" in by_event["e_back"]["fixed_ids"]
    assert result["policy"]["carry_count"] == 0
    assert all(
        135 <= placement["y"] < 610
        and 210 <= placement["x"] <= 1070
        and .54 <= placement["scale"] <= .5625
        for row in result["events"] for placement in row["placements"]
    )


def test_original_profile_remains_backward_compatible():
    board, plan, cues, policy = sample()
    legacy = dict(policy)
    for key in ("board_mode","board_column_width_px","math_base_scale",
                "math_min_scale","row_gap_px","guidance_style"):
        legacy.pop(key)
    assert "board_mode" not in legacy
    result = build_longboard_plan(board,plan,policy=legacy,
        measure=lambda latex, h:GlyphSize(150,35))
    assert result["policy"]["board_mode"]=="classic"
    assert result["policy"]["math_base_scale"] == 1.


def test_reference_classroom_four_categories_have_stable_distinct_colors():
    phases = ("strategy","knowledge","pitfall","summary")
    colors = [BOARD_TEXT_STYLE[name]["heading"] for name in phases]
    assert len(set(colors)) == len(phases)
    assert set(phases).issubset(BOARD_GUIDANCE_PHASES)
    assert [BOARD_TEXT_STYLE[name]["font_px"] for name in phases] == [17]*4
    assert BOARD_DETAIL_FONT_PX == 15
    assert BOARD_DERIVATION_INK == "#111111"
    board, plan, cues, policy = sample()
    assert any(c["phase"]=="pitfall" for c in cues["events"])
    assert policy["content_top_offset_px"] == 0


def test_detect_crossing_formula_paths_before_animating():
    a = {"x":300.,"y":200.,"w":110.,"h":26.}
    b = {"x":600.,"y":200.,"w":110.,"h":26.}
    original = {"formula_one":a,"formula_two":b}
    swapped = {"formula_one":b,"formula_two":a}
    assert interpolated_collisions(original,swapped), "crossing path must be guarded"
    shifted = {
        "formula_one":{"x":300.,"y":250.,"w":110.,"h":26.},
        "formula_two":{"x":600.,"y":250.,"w":110.,"h":26.},
    }
    assert interpolated_collisions(original,shifted)==[]
    assert math_placement_collisions([
        {"object_id":k,**v} for k,v in shifted.items()
    ])==[]


def test_reject_overlapping_final_math_boxes():
    candidates=[
        {"object_id":"A","x":320.,"y":220.,"w":120.,"h":35.},
        {"object_id":"B","x":330.,"y":240.,"w":120.,"h":35.},
    ]
    assert math_placement_collisions(candidates)==[("A","B")]
