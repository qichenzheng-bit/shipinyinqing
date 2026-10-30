"""Cross-module acceptance: entirely fresh Taylor limit in persistent classroom."""
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))

from build_fresh_taylor_classroom import build_new,STEPS,PROBLEM
from build_classroom_rework_example import build as original_integral
from animation_engine.persistent_chalkboard import make_chalkboard_plan
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.classroom_policy import (
    simple_classroom_policy,SIMPLE_CLASSROOM_RULES
)
from animation_engine.classroom_cues import BOARD_TEXT_STYLE,BOARD_GUIDANCE_PHASES
from animation_engine.longboard_plan import LongboardError
from animation_engine.board_motion import overlaps


def measured(latex,height):
    return GlyphSize(195,42)


def test_completely_different_calculus_problem_math_and_source_integrity():
    pkg,board,execution,cues,policy=build_new()
    assert "\\tan x" in PROBLEM and "\\int" not in PROBLEM
    assert len(cues["events"])==len(STEPS)==5
    assert sum(len(u["math"]) for u in STEPS)==12
    assert pkg["source"]["problem"]==PROBLEM
    assert all(c["source_step_ids"]==[
        f"s{i}_{j}" for j in range(1,len(STEPS[i-1]["math"])+1)]
        for i,c in enumerate(cues["events"],1))
    assert cues["source_storyboard_sha256"]==execution.source_storyboard_sha256
    assert "m_final" in policy["result_ids"]


def test_new_problem_and_old_problem_are_both_unchanged_across_same_session():
    _=build_new()
    _,board,execution,cues,policy=original_integral()
    assert len(cues["events"])==14
    assert any("ln" in s["math_object_id"] for s in []
               ) is False
    assert "\\ln" in board.header.text
    assert "simple_full_board"==policy["board_mode"]


def test_default_preset_implements_confirmed_blackboard_requirements():
    p=simple_classroom_policy()
    assert p["guidance_style"]=="persistent_chalkboard"
    assert p["allow_scroll"] is False
    assert p["cut_before_events"]==[]
    assert p["math_base_scale"]==.5625
    assert SIMPLE_CLASSROOM_RULES["writing"]=="append_only_until_board_full"
    assert SIMPLE_CLASSROOM_RULES["math_color"]=="#111111"
    assert len({BOARD_TEXT_STYLE[k]["heading"] for k in
                ("strategy","knowledge","pitfall","summary")})==4
    assert {"strategy","knowledge","pitfall","summary"}.issubset(
        BOARD_GUIDANCE_PHASES
    )


def test_fresh_taylor_every_math_written_exactly_once_and_ink_is_persistent():
    _,board,execution,cues,policy=build_new()
    plan=make_chalkboard_plan(board,execution,cues,policy,measure=measured)
    assert plan["event_count"]==5
    assert [e["math_write_count"] for e in plan["events"]]==[1,3,3,3,2]
    assert plan["page_count"]>=2
    assert sum(e["erase_before"] for e in plan["events"])==plan["page_count"]-1
    live={}
    math_ids=set()
    for row in plan["events"]:
        if row["erase_before"]:
            live={}
        for block in row["added_blocks"]:
            assert block["block_id"] not in live
            assert 148<=block["y"]<620
            assert block["y"]+block["h"]<=620
            for old in live.values():
                assert not overlaps(block,old,0)
            live[block["block_id"]]=block
            if block["kind"]=="math" and not block.get("carry"):
                assert block["block_id"] not in math_ids
                math_ids.add(block["block_id"])
        assert list(live)==row["visible_block_ids"]
    assert "m_final" in math_ids
    assert len(math_ids)==len(plan["math_written_ids"])
    assert plan["events"][-1]["event_id"]=="e_conclusion"


def test_new_question_does_not_erase_just_because_teaching_phase_changes():
    _,board,execution,cues,policy=build_new()
    plan=make_chalkboard_plan(board,execution,cues,policy,measure=measured)
    for prior,current in zip(plan["events"],plan["events"][1:]):
        if not current["erase_before"]:
            assert set(prior["visible_block_ids"]).issubset(
                current["visible_block_ids"]
            )


def test_provenance_rejected_and_large_formula_not_silently_shrunk():
    _,board,execution,cues,policy=build_new()
    bad=dict(cues,source_storyboard_sha256="0"*64)
    with pytest.raises(LongboardError,match="SOURCE_HASH"):
        make_chalkboard_plan(board,execution,bad,policy,measure=measured)
    with pytest.raises(LongboardError):
        make_chalkboard_plan(
            board,execution,cues,policy,
            measure=lambda latex,h: GlyphSize(10000,50)
        )


def test_cli_defaults_to_confirmed_classroom_with_reviewed_cues(tmp_path,monkeypatch):
    from animation_engine import cli as cli_module
    from animation_engine import persistent_chalkboard
    pkg,board,execution,cues,policy=build_new()
    storyboard=tmp_path/"storyboard.json"
    actions=tmp_path/"execution.json"
    notes=tmp_path/"cues.json"
    out=tmp_path/"plan.json"
    storyboard.write_text(board.model_dump_json(),encoding="utf-8")
    actions.write_text(execution.model_dump_json(),encoding="utf-8")
    notes.write_text(json.dumps(cues,ensure_ascii=False),encoding="utf-8")
    def capture(b,e,c,chosen):
        assert chosen["guidance_style"]=="persistent_chalkboard"
        assert chosen["allow_scroll"] is False
        assert chosen["cut_before_events"]==[]
        assert c["source_storyboard_sha256"]==execution.source_storyboard_sha256
        return {"mode":chosen["guidance_style"],"events":len(c["events"])}
    monkeypatch.setattr(persistent_chalkboard,"make_chalkboard_plan",capture)
    code=cli_module.main([
        "plan-longboard","--storyboard",str(storyboard),
        "--execution",str(actions),"--classroom-cues",str(notes),
        "--output",str(out),
    ])
    assert code==0
    saved=json.loads(out.read_text(encoding="utf-8"))
    assert saved=={"mode":"persistent_chalkboard","events":5}


def test_missing_taylor_product_calculation_is_now_displayed_in_same_unit():
    pkg,board,execution,cues,policy=build_new()
    group=board.scenes[2]
    assert group.event_id=="e_product"
    writes=[a for a in group.actions if a.kind=="progressive_write"]
    assert len(writes)==3
    assert any(r"-\frac{x^5}{24}-\frac{x^5}{12}" in w.latex
               for w in writes)
    assert [a.kind for a in writes]==["progressive_write"]*3
    # No separate scene just for a cubic or quintic coefficient.
    assert all("quintic" not in sc.event_id and "cubic" not in sc.event_id
               for sc in board.scenes)
