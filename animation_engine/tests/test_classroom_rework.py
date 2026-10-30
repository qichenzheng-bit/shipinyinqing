"""Classroom-led redesign contract tests: not visual proof by themselves."""
import copy
import pytest
from animation_engine.classroom_cues import checked_cues
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


def test_new_problem_has_real_full_page_transitions_and_preserves_last_math():
    board, plan, cues, policy=sample()
    result=build_longboard_plan(board,plan,policy=policy,
        measure=lambda latex,height: GlyphSize(195,46))
    assert len(result["events"])==14
    assert set(["e_division","e_back"]).issubset({
        r["event_id"] for r in result["events"] if r["transition"]=="cut"
    })
    assert result["events"][-1]["new_ids"]==["m_final"]
    assert result["policy"]["content_top_offset_px"]==112
    assert all(
        placement["y"]>=232 for row in result["events"]
        for placement in row["placements"]
    )
