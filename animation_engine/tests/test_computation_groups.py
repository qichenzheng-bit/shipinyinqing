"""V2.5.1 contract, ordering, semantic carries and whole-subgoal erasure."""
import copy
import sys
from pathlib import Path

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from build_multipart_integral_lesson import build_variant
from animation_engine.computation_groups import checked_computation_groups
from animation_engine.persistent_chalkboard import make_chalkboard_plan
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.longboard_plan import LongboardError
from animation_engine.board_motion import overlaps


def measure(latex,pixel_height):
    return GlyphSize(240,42)


@pytest.mark.parametrize("variant,parts,groups",[
    ("A",3,5),("B",3,6),("C",5,7),
])
def test_source_contract_and_exactly_covered_subproblems(variant,parts,groups):
    pkg,board,execution,cues,policy,manifest,units,problem,result=build_variant(variant)
    groups_contract=checked_computation_groups(manifest,board,execution)
    assert len(groups_contract.parts)==parts
    assert len(board.scenes)==len(units)==groups
    assert groups_contract.decomposition_object_id=="m_decomposition"
    assert groups_contract.final_object_id=="m_final"
    assert len({p.result_id for p in groups_contract.parts})==parts
    assert pkg["source"]["problem"]==problem
    layout=make_chalkboard_plan(
        board,execution,cues,policy,measure=measure,
        computation_manifest=manifest
    )
    assert layout["computation_groups"]["part_count"]==parts
    assert layout["event_count"]==groups
    assert layout["page_count"]>=2
    assert set(layout["math_written_ids"])=={
        m["math_object_id"] for m in pkg["lesson"]["math_objects"]
    }
    assert layout["events"][-1]["computation_role"]=="final"
    assert layout["events"][0]["computation_role"]=="decomposition"
    assert layout["events"][-1]["erase_reason"] in (
        None,"whole_reasoning_unit_cannot_fit"
    )


def test_pages_contain_only_source_objects_and_results_are_written_before_final():
    pkg,board,exec,cues,policy,manifest,units,problem,result=build_variant("A")
    plan=make_chalkboard_plan(
        board,exec,cues,policy,measure=measure,
        computation_manifest=manifest
    )
    written=set()
    active={}
    results=[p["result_object_id"] for p in manifest["parts"]]
    for row in plan["events"]:
        if row["erase_before"]:
            active={}
            assert row["erase_reason"]=="whole_reasoning_unit_cannot_fit"
            assert all(mid in written for mid in row["carry_object_ids"])
        if row["event_id"]=="e_final":
            assert set(results).issubset(written)
        for block in row["added_blocks"]:
            assert block["block_id"] not in active
            assert all(not overlaps(block,old,margin=0)
                       for old in active.values())
            active[block["block_id"]]=block
            if block["kind"]=="math" and not block.get("carry"):
                assert block["block_id"] not in written
                written.add(block["block_id"])
        assert row["visible_block_ids"]==list(active)
    assert "m_final" in written
    assert len(results)==len(set(results))


def test_long_second_integral_uses_only_approved_intermediate_checkpoint():
    pkg,board,execution,cues,policy,manifest,units,problem,result=build_variant("B")
    plan=make_chalkboard_plan(
        board,execution,cues,policy,
        measure=lambda latex,h:GlyphSize(235,63),
        computation_manifest=manifest
    )
    phase1=next(r for r in plan["events"] if r["event_id"]=="e_i2start")
    phase2=next(r for r in plan["events"] if r["event_id"]=="e_i2finish")
    assert phase2["erase_before"],plan
    assert phase2["page_index"]==phase1["page_index"]+1
    assert "m_i2_checkpoint" in phase2["carry_object_ids"]
    assert "m_i1_result" in phase2["carry_object_ids"]
    assert "m_decomposition" in phase2["carry_object_ids"]
    assert not any(b["kind"]=="math" and
                   b["block_id"]=="m_i2_result" and b.get("carry")
                   for b in phase2["added_blocks"])
    assert phase2["math_write_count"]==3


def test_mid_part_page_break_without_teacher_approved_checkpoint_rejected():
    _,board,execution,cues,policy,manifest,_,_,_=build_variant("B")
    broken=copy.deepcopy(manifest)
    broken["parts"][1]["safe_break_after"]=[]
    broken["parts"][1]["checkpoints"]=[]
    with pytest.raises(LongboardError,match="COMPUTATION_NO_SAFE_BREAK"):
        make_chalkboard_plan(
            board,execution,cues,policy,
            measure=lambda latex,h:GlyphSize(235,63),
            computation_manifest=broken
        )


def test_mandatory_context_not_dropped_to_make_a_page_fit():
    _,board,execution,cues,policy,manifest,_,_,_=build_variant("B")
    with pytest.raises(LongboardError,match="COMPUTATION_MANDATORY_CARRY_OVERFLOW"):
        make_chalkboard_plan(
            board,execution,cues,policy,
            measure=lambda latex,h:GlyphSize(220,74),
            computation_manifest=manifest
        )


@pytest.mark.parametrize("mutation,expected",[
    ("hash","SOURCE_HASH"),
    ("unreviewed","NEED_TEACHER_REVIEW"),
    ("early_result","RESULT_NOT_LAST_STEP"),
    ("duplicate_part","DUPLICATE_PART_ID"),
    ("missing_event","EVENTS_MISSING_OR_UNORDERED"),
    ("wrong_checkpoint","CHECKPOINT_NOT_FINAL_IN_EVENT"),
])
def test_invalid_source_and_semantics_fail_closed(mutation,expected):
    pkg,board,execution,cues,policy,manifest,units,problem,result=build_variant("B")
    changed=copy.deepcopy(manifest)
    if mutation=="hash":
        changed["source_storyboard_sha256"]="0"*64
    elif mutation=="unreviewed":
        changed["teacher_reviewed"]=False
    elif mutation=="early_result":
        changed["parts"][1]["result_object_id"]="m_i2_j_parts"
    elif mutation=="duplicate_part":
        changed["parts"][2]["id"]="I2"
    elif mutation=="missing_event":
        changed["parts"]=changed["parts"][:2]
    elif mutation=="wrong_checkpoint":
        changed["parts"][1]["checkpoints"][0]["object_id"]="m_i2_first_parts"
    with pytest.raises(LongboardError,match=expected):
        checked_computation_groups(changed,board,execution)


def test_existing_ordinary_classroom_without_groups_unchanged():
    pkg,board,execution,cues,policy,manifest,units,problem,result=build_variant("A")
    plain=make_chalkboard_plan(board,execution,cues,policy,measure=measure)
    grouped=make_chalkboard_plan(
        board,execution,cues,policy,measure=measure,
        computation_manifest=manifest
    )
    assert plain["event_count"]==grouped["event_count"]
    assert "computation_groups" not in plain
    assert len(grouped["math_written_ids"])==len(plain["math_written_ids"])
    assert grouped["events"][-1]["computation_role"]=="final"
