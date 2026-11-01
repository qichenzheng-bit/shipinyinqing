"""V2.5.4 diagram origin, correct area, dot labels and animated lifecycle."""
from __future__ import annotations
import copy
import json
import math
import sys
from pathlib import Path

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))

from build_diagram_classroom_lesson import build_variant,export_variant
from animation_engine.diagram_classroom import (
    DIAGRAM_PANEL,DIAGRAM_FORMULA_X,DIAGRAM_FORMULA_W,
    checked_diagram_classroom
)
from animation_engine.persistent_chalkboard import make_chalkboard_plan
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.longboard_plan import LongboardError
from animation_engine.board_motion import overlaps
from animation_engine.core_knowledge import checked_core_knowledge


def measure(tex,height):
    return GlyphSize(180,39)


@pytest.mark.parametrize("variant,kind,events",[
    ("A","function_graph",5),
    ("B","integration_region",6),
    ("C","geometry_proof",5),
])
def test_diagrams_have_frozen_source_and_stage_by_stage_reveal(
        variant,kind,events):
    package,board,exe,cues,policy,manifest,units,catalog=build_variant(variant)
    checked_core_knowledge(units,catalog)
    verified=checked_diagram_classroom(manifest,board,exe)
    assert verified.kind==kind
    assert len(verified.stages)==events
    assert board.scenes[0].diagram is not None
    plan=make_chalkboard_plan(
        board,exe,cues,policy,measure=measure,diagram_manifest=manifest
    )
    assert plan["diagram_classroom"]["source_verified"]
    assert plan["diagram_classroom"]["staged_reveal_not_inferred"]
    assert plan["diagram_classroom"]["all_revealed"]
    assert plan["alignment"]["mode"]=="diagram_left_math_right_geometry"
    assert len(plan["events"])==events
    shown=[]
    active={}
    for event in plan["events"]:
        if event["erase_before"]:
            active={}
            assert event["diagram_carry_ids"]==shown
        else:
            assert not event["diagram_carry_ids"]
        revealed=event["diagram_reveal_ids"]
        assert all(k not in shown for k in revealed)
        shown.extend(revealed)
        assert event["visible_diagram_ids"]==shown
        for block in event["added_blocks"]:
            assert block["block_id"] not in active
            assert all(not overlaps(block,x,margin=0) for x in active.values())
            assert block["y"]+block["h"]<=620
            assert block["x"]>=DIAGRAM_FORMULA_X-1
            assert block["x"]+block["w"]<=(
                DIAGRAM_FORMULA_X+DIAGRAM_FORMULA_W+1)
            active[block["block_id"]]=block
        assert event["visible_block_ids"]==list(active)
    assert set(shown)==set(verified.objects)



@pytest.mark.parametrize("variant",["A","B","C"])
def test_auxiliary_coordinates_are_not_displayed_as_unwanted_dots(variant):
    _,board,exe,cues,policy,manifest,units,catalog=build_variant(variant)
    check=checked_diagram_classroom(manifest,board,exe)
    labels={p.id for p in board.scenes[0].diagram.points if p.label}
    for p in board.scenes[0].diagram.points:
        assert check.objects[p.id]["kind"]==(
            "point" if p.id in labels else "coordinate"
        )
    if variant=="C":
        assert all(check.objects[x]["kind"]=="coordinate"
                   for x in ("U","V","W"))


def test_integral_page_two_retains_formula_and_previous_area_work():
    _,board,exe,cues,policy,manifest,units,catalog=build_variant("B")
    plan=make_chalkboard_plan(
        board,exe,cues,policy,measure=lambda tex,height:GlyphSize(205,55),
        diagram_manifest=manifest
    )
    if plan["page_count"]==1:
        pytest.skip("Mock glyphs happened to fit one page")
    second=next(e for e in plan["events"] if e["erase_before"])
    ids=second["carry_object_ids"]
    assert "m_area_rule" in ids and "m_area_step" in ids
    for block in second["added_blocks"]:
        if block.get("carry"):
            assert abs((block["x"]+block["w"]/2)-
                       (DIAGRAM_FORMULA_X+DIAGRAM_FORMULA_W/2))<1
    assert len(second["diagram_carry_ids"])>0


def test_graph_coordinates_have_real_parabola_and_tangent_derivative():
    _,b,e,c,p,m,u,k=build_variant("A")
    source=b.scenes[0].diagram
    curve=next(x for x in source.curves if x.id=="parabola")
    for x,y in curve.points:
        raw_x=(x-.18)/.32
        assert abs(y-(.78-.16*raw_x*raw_x))<1e-5
    points={x.id:x for x in source.points}
    p=points["P"]
    assert (p.x,p.y)==(.50,.62)
    t0,t1=points["T0"],points["T1"]
    dx=(t1.x-t0.x)/.32
    dy=-(t1.y-t0.y)/.16
    assert abs(dy/dx-2)<1e-7


def test_shading_reuses_two_actual_curves_and_has_correct_integral():
    import sympy as s
    _,b,e,c,p,m,u,k=build_variant("B")
    verified=checked_diagram_classroom(m,b,e)
    area=verified.objects["shade_between"]
    assert len(area["boundary"])==34
    assert area["kind"]=="region"
    x=s.symbols("x",real=True)
    assert s.integrate(x-x*x,(x,0,1))==s.Rational(1,6)
    assert [x for x in verified.ordered_ids if x=="shade_between"]==[
        "shade_between"
    ]


def test_actual_geometry_side_lengths_follow_three_four_five():
    _,board,exe,cues,policy,manifest,units,catalog=build_variant("C")
    pts={p.id:p for p in board.scenes[0].diagram.points}
    def distance(a,b):
        x=(pts[a].x-pts[b].x)*DIAGRAM_PANEL["w"]
        y=(pts[a].y-pts[b].y)*DIAGRAM_PANEL["h"]
        return math.hypot(x,y)
    assert abs(distance("A","B")-224)<.01
    assert abs(distance("A","C")-168)<.01
    assert abs(distance("B","C")-280)<.01
    assert abs((pts["B"].x-pts["A"].x)*(pts["C"].x-pts["A"].x)
               +(pts["B"].y-pts["A"].y)*(pts["C"].y-pts["A"].y))<.00001


@pytest.mark.parametrize("variant",["A","B","C"])
def test_missing_diagram_contract_must_fail_not_fake_render(variant):
    _,board,exe,cues,policy,manifest,_,_=build_variant(variant)
    with pytest.raises(LongboardError,match="CHALKBOARD_UNSUPPORTED_SPECIAL_LAYOUT"):
        make_chalkboard_plan(board,exe,cues,policy,measure=measure)


def test_tampered_source_or_unknown_diagram_reveal_fails_closed():
    _,b,e,c,p,m,u,k=build_variant("A")
    bad=copy.deepcopy(m)
    bad["source_storyboard_sha256"]="0"*64
    with pytest.raises(LongboardError,match="DIAGRAM_SOURCE_HASH"):
        checked_diagram_classroom(bad,b,e)
    bad=copy.deepcopy(m)
    bad["stages"][0]["reveal_ids"].append("phantom")
    with pytest.raises(LongboardError,match="DIAGRAM_REVEAL_UNKNOWN_OBJECT"):
        checked_diagram_classroom(bad,b,e)
    bad=copy.deepcopy(m)
    bad["stages"][0]["reveal_ids"].remove("axis_y")
    with pytest.raises(LongboardError,match="DIAGRAM_INCOMPLETE_REVEAL"):
        checked_diagram_classroom(bad,b,e)


def test_label_cannot_appear_ahead_of_its_source_point():
    _,b,e,c,p,m,u,k=build_variant("A")
    bad=copy.deepcopy(m)
    bad["stages"][0]["reveal_ids"].append("label:P")
    bad["stages"][1]["reveal_ids"].remove("label:P")
    with pytest.raises(LongboardError,match="DIAGRAM_LABEL_BEFORE_POINT"):
        checked_diagram_classroom(bad,b,e)


def test_filled_region_cannot_appear_before_its_boundary_curves():
    _,b,e,c,p,m,u,k=build_variant("B")
    bad=copy.deepcopy(m)
    bad["stages"][3]["reveal_ids"].remove("shade_between")
    bad["stages"][0]["reveal_ids"].append("shade_between")
    with pytest.raises(LongboardError,match="DIAGRAM_REGION_BEFORE_BOUNDARY_CURVES"):
        checked_diagram_classroom(bad,b,e)
    bad=copy.deepcopy(m)
    bad["filled_regions"][0]["upper_curve_id"]="lower_parabola"
    bad["filled_regions"][0]["lower_curve_id"]="upper_line"
    with pytest.raises(LongboardError,match="DIAGRAM_REGION_UPPER_BELOW_LOWER"):
        checked_diagram_classroom(bad,b,e)


def test_mutual_exclusion_of_matrix_proof_and_diagram_contract():
    _,b,e,c,p,m,u,k=build_variant("C")
    with pytest.raises(LongboardError,match="CHALKBOARD_MULTIPLE_SPECIAL_CONTRACTS"):
        make_chalkboard_plan(
            b,e,c,p,measure=measure,diagram_manifest=m,
            matrix_manifest={"schema_version":"1.0"}
        )


@pytest.mark.parametrize("variant",["A","B","C"])
def test_diagram_source_export_is_complete_and_reproducible(tmp_path,variant):
    path=tmp_path/variant
    export_variant(path,variant)
    manifest=json.loads((path/"diagram_classroom.json").read_text())
    execution=json.loads((path/"execution.json").read_text())
    storyboard=json.loads((path/"storyboard.json").read_text())
    contract=checked_diagram_classroom(manifest,storyboard,execution)
    assert len(contract.ordered_ids)>=5
    assert manifest["teacher_reviewed"] is True
    assert (path/"core_knowledge.json").is_file()
