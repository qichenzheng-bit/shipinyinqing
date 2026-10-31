"""Every integral method needs visible source-verified knowledge and real formula.

This is a classroom-layout regression, not AI-generated math assessment.
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from build_multipart_integral_lesson import build_variant
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.persistent_chalkboard import (
    make_chalkboard_plan, BOARD_X, BOARD_WIDTH,
    KNOWLEDGE_WIDTH, KNOWLEDGE_GUTTER,
)
from animation_engine.computation_groups import checked_computation_groups


def measure(latex, height):
    return GlyphSize(240, 42)


@pytest.mark.parametrize("variant,expected", [("A",3),("B",3),("C",5)])
def test_every_individual_integral_has_written_rule_and_side_by_side_work(
        variant, expected):
    pkg, board, execution, cues, policy, manifest, units, _, _=build_variant(variant)
    groups=checked_computation_groups(manifest,board,execution)
    layout=make_chalkboard_plan(
        board,execution,cues,policy,measure=measure,computation_manifest=manifest
    )
    by_id={e["event_id"]:e for e in layout["events"]}
    cue_by_id={c["event_id"]:c for c in cues["events"]}
    source={m["math_object_id"]:m["latex"] for m in pkg["lesson"]["math_objects"]}
    assert len(groups.parts)==expected
    assert BOARD_X < 200 and BOARD_WIDTH >= 1000
    assert policy["math_base_scale"] <= 0.50
    for part in groups.parts:
        first_event=part.event_ids[0]
        first=by_id[first_event]
        knowledge=part.knowledge_object_id
        assert knowledge is not None
        assert cue_by_id[first_event]["phase"]=="knowledge"
        assert source[knowledge].startswith(r"\int")
        notes=[b for b in first["added_blocks"] if b["kind"]=="teacher_note"]
        assert len(notes)==1
        assert notes[0]["heading"].startswith("核心知识点")
        assert notes[0]["w"]==KNOWLEDGE_WIDTH
        formulas=[b for b in first["added_blocks"]
                  if b["kind"]=="math" and not b.get("carry")]
        assert len(formulas)>=2
        assert formulas[0]["block_id"]==knowledge
        assert abs(formulas[0]["x"]-notes[0]["x"]) <= 0.01
        assert all(b["x"]>=notes[0]["x"]+KNOWLEDGE_WIDTH+KNOWLEDGE_GUTTER-0.01
                   for b in formulas[1:])
        assert formulas[-1]["block_id"]==(
            part.result_id if len(part.event_ids)==1
            else "m_i2_checkpoint"
        )
        assert all(b["scale"]<=0.50 for b in formulas)
    assert set(layout["math_written_ids"])==set(source)
    # Both single-column and paired units are centered as a group, not
    # pinned to the left just because blank canvas exists on the right.
    from animation_engine.persistent_chalkboard import _ink_width, BOARD_CENTER_X
    for event in layout["events"]:
        blocks=[b for b in event["added_blocks"] if not b.get("carry")]
        if not blocks:
            continue
        left=min(b["x"] for b in blocks)
        right=max(b["x"]+_ink_width(b) for b in blocks)
        assert abs((left+right)/2-BOARD_CENTER_X)<1.0, (variant,event["event_id"])
    assert all(abs(p["ink_center_x"]-BOARD_CENTER_X)<1.0
               for p in layout["alignment"]["pages"])


def test_nested_integration_by_parts_restates_knowledge_when_continuing():
    pkg,board,execution,cues,policy,manifest,_,_,_=build_variant("B")
    layout=make_chalkboard_plan(
        board,execution,cues,policy,measure=measure,computation_manifest=manifest
    )
    finish=next(e for e in layout["events"] if e["event_id"]=="e_i2finish")
    note=next(b for b in finish["added_blocks"] if b["kind"]=="teacher_note")
    assert note["heading"].startswith("核心知识点")
    math_ids=[b["block_id"] for b in finish["added_blocks"]
              if b["kind"]=="math" and not b.get("carry")]
    assert math_ids[0]=="m_b_i2_j_rule"
    assert "m_b_i2_j_choice" in math_ids
    assert math_ids[-1]=="m_i2_result"
