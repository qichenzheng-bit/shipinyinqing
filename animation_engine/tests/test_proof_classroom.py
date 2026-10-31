"""V2.5.3 proof source order, case closure and full-board continuity tests."""
from __future__ import annotations
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))

from build_proof_classroom_lesson import build_variant
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.board_motion import overlaps
from animation_engine.longboard_plan import LongboardError
from animation_engine.proof_chain import checked_proof_chain
from animation_engine.persistent_chalkboard import (
    make_chalkboard_plan, BOARD_CENTER_X, BOARD_BOTTOM_Y, _ink_width
)


def measure(tex,height):
    return GlyphSize(210, 47)


@pytest.mark.parametrize("variant,stages,groups", [
    ("A",8,0),("B",7,0),("C",8,1)
])
def test_proof_stages_source_integrity_and_safe_pagination(variant,stages,groups):
    package,board,execution,cues,policy,manifest,units=build_variant(variant)
    proof=checked_proof_chain(manifest,board,execution)
    assert len(proof.stages)==stages
    assert len(proof.branch_groups)==groups
    plan=make_chalkboard_plan(
        board,execution,cues,policy,measure=measure,proof_manifest=manifest
    )
    assert plan["proof_chain"]["stage_count"]==stages
    assert plan["proof_chain"]["reference_order_verified"]
    assert plan["proof_chain"]["case_coverage_verified"]
    assert plan["proof_chain"]["mathematical_truth_status"]==(
        "teacher_reviewed_not_formally_proven"
    )
    assert plan["event_count"]==stages
    assert [e["event_id"] for e in plan["events"]]==[
        "e_"+u["id"] for u in units
    ]
    assert plan["alignment"]["mode"]=="each_unit_centered_with_header_near_top"
    assert all(p["first_ink_y"]<=plan["alignment"]["max_first_ink_y"]
               for p in plan["alignment"]["pages"])
    live={}
    crossed=0
    for ev in plan["events"]:
        if ev["erase_before"]:
            crossed+=1
            live={}
            carry_ids=set(ev["carry_object_ids"]) if ev["carry_object_ids"] else {
                b["block_id"] for b in ev["added_blocks"] if b.get("carry")
            }
            assert {"m_condition","m_goal"}<=carry_ids
            assert set(ev["proof_cites"])<=carry_ids
            prior=plan["events"][plan["events"].index(ev)-1]
            assert prior["safe_break_after"]
        blocks=[b for b in ev["added_blocks"] if not b.get("carry")]
        assert blocks
        assert abs((min(b["x"] for b in blocks)+
                    max(b["x"]+_ink_width(b) for b in blocks))/2
                   -BOARD_CENTER_X)<1
        for block in ev["added_blocks"]:
            assert block["block_id"] not in live
            assert all(not overlaps(block,b,margin=0) for b in live.values())
            assert block["y"]+block["h"]<=BOARD_BOTTOM_Y+.01
            if block["kind"]=="math":
                assert block["fragments"]
                assert abs(block["fragments"][0]["x"]-block["x"])<.01
                assert abs(block["fragments"][0]["y"]-block["y"])<.01
            live[block["block_id"]]=block
        assert ev["visible_block_ids"]==list(live)
    assert crossed==plan["page_count"]-1
    assert set(plan["math_written_ids"])=={
        obj["math_object_id"] for obj in package["lesson"]["math_objects"]
    }


def test_long_induction_has_full_explicit_derivation_without_false_shortcuts():
    _,b,e,c,p,m,u=build_variant("A")
    proof=checked_proof_chain(m,b,e)
    assert proof.stages[0].output_ids==(
        "m_condition","m_definition","m_goal"
    )
    ids=set(x for stage in proof.stages for x in stage.output_ids)
    for must in (
        "m_base_result","m_hypothesis","m_successor_split",
        "m_successor_subst","m_factor_result","m_lemma_result",
        "m_successor_result","m_final"
    ):
        assert must in ids
    assert "m_lemma_result" in proof.for_event("e_successor_done").cites
    assert "m_base_result" in proof.for_event("e_final").cites


def test_parameter_all_cases_are_explicit_and_merged_before_final():
    _,b,e,c,p,m,u=build_variant("C")
    proof=checked_proof_chain(m,b,e)
    assert proof.branch_groups[0]["cases"]==["less","equal","greater"]
    merge=proof.for_event("e_merge")
    assert {"m_less_result","m_equal_result","m_greater_result"}<=set(merge.cites)
    assert "m_merge" in proof.for_event("e_final").cites


def test_source_hash_unapproved_and_early_references_fail_closed():
    _,b,e,c,p,m,_=build_variant("A")
    bad=copy.deepcopy(m);bad["teacher_reviewed"]=False
    with pytest.raises(LongboardError,match="PROOF_INVALID_MANIFEST"):
        checked_proof_chain(bad,b,e)
    bad=copy.deepcopy(m);bad["source_storyboard_sha256"]="0"*64
    with pytest.raises(LongboardError,match="PROOF_SOURCE_HASH"):
        checked_proof_chain(bad,b,e)
    bad=copy.deepcopy(m)
    bad["stages"][1]["cites"]=["m_successor_result"]
    bad["stages"][1]["carry_ids"].append("m_successor_result")
    with pytest.raises(LongboardError,match="PROOF_PREMATURE_REFERENCE"):
        checked_proof_chain(bad,b,e)


def test_future_carry_and_missing_goal_are_disallowed():
    _,b,e,c,p,m,_=build_variant("B")
    bad=copy.deepcopy(m)
    bad["stages"][2]["carry_ids"].append("m_final")
    with pytest.raises(LongboardError,match="PROOF_PREMATURE_CARRY"):
        checked_proof_chain(bad,b,e)
    bad=copy.deepcopy(m)
    bad["stages"][2]["carry_ids"].remove("m_goal")
    with pytest.raises(LongboardError,match="PROOF_REQUIRED_CONTEXT_MISSING"):
        checked_proof_chain(bad,b,e)


def test_all_branches_required_before_merged_conclusion():
    _,b,e,c,p,m,_=build_variant("C")
    bad=copy.deepcopy(m)
    bad["branch_groups"][0]["cases"].remove("equal")
    with pytest.raises(LongboardError,match="PROOF_MISSING_OR_EXTRA_CASES"):
        checked_proof_chain(bad,b,e)
    bad=copy.deepcopy(m)
    bad["stages"][6]["cites"].remove("m_equal_result")
    bad["stages"][6]["carry_ids"].remove("m_equal_result")
    with pytest.raises(LongboardError,match="PROOF_INCOMPLETE_BRANCH_MERGE"):
        checked_proof_chain(bad,b,e)
    bad=copy.deepcopy(m)
    bad["stages"][4]["cites"].append("m_less_result")
    bad["stages"][4]["carry_ids"].append("m_less_result")
    with pytest.raises(LongboardError,match="PROOF_CASE_CROSS_REFERENCE"):
        checked_proof_chain(bad,b,e)


def test_wrong_mathematics_source_ids_or_skipped_stage_are_rejected():
    _,b,e,c,p,m,_=build_variant("A")
    bad=copy.deepcopy(m)
    bad["stages"][3]["output_ids"].remove("m_successor_split")
    with pytest.raises(LongboardError,match="PROOF_SOURCE_OUTPUT_MISMATCH"):
        checked_proof_chain(bad,b,e)
    bad=copy.deepcopy(m)
    bad["stages"].pop(3)
    with pytest.raises(LongboardError,match="PROOF_STAGE_COVERAGE"):
        checked_proof_chain(bad,b,e)


def test_proof_layout_requires_reviewed_manifest():
    _,b,e,c,p,m,_=build_variant("A")
    with pytest.raises(LongboardError,match="CHALKBOARD_UNSUPPORTED_SPECIAL_LAYOUT"):
        make_chalkboard_plan(b,e,c,p,measure=measure)
    with pytest.raises(LongboardError,match="CHALKBOARD_MULTIPLE_SPECIAL_CONTRACTS"):
        make_chalkboard_plan(
            b,e,c,p,measure=measure,proof_manifest=m,
            computation_manifest={"schema_version":"1.0"}
        )


def test_proof_safe_boundary_and_mandatory_carry_cannot_be_silently_skipped():
    _,b,e,c,p,m,_=build_variant("A")
    good=make_chalkboard_plan(
        b,e,c,p,measure=measure,proof_manifest=m
    )
    assert good["page_count"]>1
    bad=copy.deepcopy(m)
    for stage in bad["stages"]:
        stage["safe_break_after"]=False
    with pytest.raises(LongboardError,match="PROOF_NO_SAFE_BREAK"):
        make_chalkboard_plan(
            b,e,c,p,measure=measure,proof_manifest=bad
        )


def test_independent_symbolic_checks_of_three_authored_proof_examples():
    import sympy as s
    n,x,y,z,a=s.symbols("n x y z a",real=True)
    assert s.expand(
        n*n*(n+1)**2/s.Integer(4)+(n+1)**3 -
        (n+1)**2*(n+2)**2/s.Integer(4)
    )==0
    assert s.expand(
        3*(x*x+y*y+z*z)-(x+y+z)**2 -
        ((x-y)**2+(y-z)**2+(z-x)**2)
    )==0
    assert s.expand((x-a)**2+1-a*a-(x*x-2*a*x+1))==0
    assert s.solve_univariate_inequality(1-a*a>=0,a,relational=False)==s.Interval(-1,1)
