"""V2.5.3 proof source order, case closure and full-board continuity tests."""
from __future__ import annotations
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent/"fixtures"))

from build_proof_classroom_lesson import build_variant
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.board_motion import overlaps
from animation_engine.longboard_plan import LongboardError
from animation_engine.proof_chain import checked_proof_chain
from animation_engine.persistent_chalkboard import (
    make_chalkboard_plan, BOARD_CENTER_X, BOARD_BOTTOM_Y, BOARD_X, _ink_width
)


def measure(tex,height):
    return GlyphSize(210, 47)


@pytest.mark.parametrize("variant,stages,groups", [
    ("A",9,0),("B",8,0),("C",9,1)
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
        mathematical=[b for b in blocks if b["kind"]=="math"]
        if ev["proof_layout"]["mode"] not in ("paired_left","paired_right"):
            assert mathematical
            assert abs((min(b["x"] for b in mathematical)+
                        max(b["x"]+_ink_width(b) for b in mathematical))/2
                       -BOARD_CENTER_X)<1
        # A paired event occupies just one side of an already reserved row,
        # so only the pair's COMBINED geometry should be center-aligned.
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




@pytest.mark.parametrize("variant",["A","B","C"])
def test_each_proof_formula_row_stays_centered_when_guidance_is_left(variant):
    _,board,execution,cues,policy,manifest,units=build_variant(variant)
    plan=make_chalkboard_plan(
        board,execution,cues,policy,measure=measure,proof_manifest=manifest
    )
    assert plan["alignment"]["proof_math_independent_centered"] is True
    assert all(abs(page["ink_center_x"]-BOARD_CENTER_X)<1.01
               for page in plan["alignment"]["pages"])
    guided=[]
    for event in plan["events"]:
        blocks={b["block_id"]:b for b in event["added_blocks"]}
        note=[b for b in event["added_blocks"] if b["kind"]=="teacher_note"]
        if note:
            guided.append(event["event_id"])
            assert len(note)==1
            assert note[0]["x"]==BOARD_X
        for row in event["proof_layout"]["formula_rows"]:
            if event["proof_layout"]["mode"].startswith("paired_"):
                continue
            formulas=[blocks[mid] for mid in row]
            left=min(b["x"] for b in formulas)
            right=max(b["x"]+_ink_width(b) for b in formulas)
            assert abs((left+right)/2-BOARD_CENTER_X)<1.01, (
                variant,event["event_id"],row,left,right
            )
        if note:
            formula_blocks=[b for b in event["added_blocks"]
                            if b["kind"]=="math" and not b.get("carry")]
            assert formula_blocks
            assert max(note[0]["y"]+note[0]["h"] for _ in [0]) <= min(
                b["y"] for b in formula_blocks
            ), (variant,event["event_id"])
    assert "e_setup" in guided
    assert any("knowledge" in eid for eid in guided)
    if variant=="C":
        assert all(f"e_case_{kind}" in guided
                   for kind in ("less","equal","greater"))


def test_carry_math_rows_centered_after_full_board_erase():
    _,board,execution,cues,policy,manifest,units=build_variant("C")
    taller=lambda tex,height:GlyphSize(210,75)
    plan=make_chalkboard_plan(
        board,execution,cues,policy,measure=taller,proof_manifest=manifest
    )
    assert plan["page_count"]>1
    for event in plan["events"]:
        if event["erase_before"]:
            carry={b["block_id"]:b for b in event["added_blocks"]
                   if b.get("carry")}
            assert carry
            rows=event["proof_carry_rows"]
            assert [mid for row in rows for mid in row]==list(carry)
            for row in rows:
                left=min(carry[mid]["x"] for mid in row)
                right=max(carry[mid]["x"]+carry[mid]["w"] for mid in row)
                assert abs((left+right)/2-BOARD_CENTER_X)<1.01



def test_A_second_page_recap_grouping_and_breathing_space():
    """Regression for cramped upper part of A's second classroom board.

    Mock MathTex glyphs make the short proof fit one page; exercise the
    dedicated recap algorithm directly. Real-font CI separately verifies
    A's genuine page-two event and all its geometry.
    """
    from animation_engine.persistent_chalkboard import (
        _proof_carry_layout,_proof_math_rows
    )
    from animation_engine.longboard_plan import _sources,LongboardPolicy
    from animation_engine.classroom_policy import simple_classroom_policy
    _,board,execution,cues,policy,manifest,units=build_variant("A")
    proof=checked_proof_chain(manifest,board,execution)
    sources=_sources(execution)
    selected=LongboardPolicy.parse(simple_classroom_policy())
    carried,start,rows=_proof_carry_layout(
        ["m_condition","m_goal","m_factor_result"],
        proof,sources,selected,measure,{},148
    )
    assert rows==[["m_condition","m_goal"],["m_factor_result"]]
    math,new_bottom,_=_proof_math_rows(
        ["m_lemma_result"],sources,selected,measure,{},start
    )
    by_id={b["block_id"]:b for b in carried+math}
    condition,goal,factor,lemma=(
        by_id[mid] for mid in (
            "m_condition","m_goal","m_factor_result","m_lemma_result"
        )
    )
    assert condition["x"]+condition["w"]+35<=goal["x"]
    assert abs((condition["x"]+goal["x"]+goal["w"])/2
               -BOARD_CENTER_X)<1.01
    assert abs((factor["x"]+factor["w"]/2)-BOARD_CENTER_X)<1.01
    assert factor["y"]-(goal["y"]+goal["h"])>=25
    assert lemma["y"]-(factor["y"]+factor["h"])>=30
    assert new_bottom<=BOARD_BOTTOM_Y


@pytest.mark.parametrize("variant",["A","B","C"])
def test_proof_short_formulas_form_multi_item_rows(variant):
    _,board,exe,cues,policy,manifest,units=build_variant(variant)
    layout=make_chalkboard_plan(
        board,exe,cues,policy,measure=measure,proof_manifest=manifest
    )
    assert layout["proof_chain"]["layout_strategy"]==(
        "adaptive_short_math_rows_and_paired_proof_stages"
    )
    compact=[
        event for event in layout["events"]
        if event["proof_layout"]["mode"]=="compact_within_stage"
    ]
    assert compact, "Short mathematical facts must not all be one-per-line"
    for event in compact:
        rows=event["proof_layout"]["formula_rows"]
        assert any(len(row)>1 for row in rows)
        assert all(1<=len(row)<=3 for row in rows)
        assert [mid for row in rows for mid in row]==[
            b["block_id"] for b in event["added_blocks"] if b["kind"]=="math"
            and not b.get("carry")
        ]
        blocks={b["block_id"]:b for b in event["added_blocks"]}
        for row in rows:
            ys=[blocks[mid]["y"] for mid in row]
            heights=[blocks[mid]["h"] for mid in row]
            centers=[a+h/2 for a,h in zip(ys,heights)]
            assert max(centers)-min(centers)<1.01
            for m,n in zip(row,row[1:]):
                assert blocks[m]["x"]+blocks[m]["w"]<blocks[n]["x"]
    assert layout["proof_chain"]["compact_stage_count"]==len(compact)


@pytest.mark.parametrize("variant",["A","B","C"])
def test_adjacent_short_proof_stages_share_horizontal_band_without_reposition(
        variant):
    _,board,exe,cues,policy,manifest,units=build_variant(variant)
    layout=make_chalkboard_plan(
        board,exe,cues,policy,measure=measure,proof_manifest=manifest
    )
    events=layout["events"]
    groups={}
    for i,event in enumerate(events):
        meta=event["proof_layout"]
        if meta["mode"].startswith("paired_"):
            groups.setdefault(meta["row_group_id"],[]).append((i,event))
    if variant in ("A","B"):
        assert groups, "Consecutive short proof steps should use left/right"
    for group,items in groups.items():
        assert len(items)==2
        (li,left),(ri,right)=items
        assert ri==li+1, "Paired proof steps are consecutive in source order"
        assert left["page_index"]==right["page_index"]
        assert not right["erase_before"]
        assert left["proof_layout"]["mode"]=="paired_left"
        assert right["proof_layout"]["mode"]=="paired_right"
        assert left["proof_layout"]["source_order_preserved"]
        assert right["proof_layout"]["source_order_preserved"]
        la=[block for block in left["added_blocks"] if block["kind"]=="math"
            and not block.get("carry")]
        ra=[block for block in right["added_blocks"] if block["kind"]=="math"
            and not block.get("carry")]
        assert la and ra
        assert max(b["x"]+b["w"] for b in la)<min(b["x"] for b in ra)
        left_x=min(b["x"] for b in la)
        right_x=max(b["x"]+_ink_width(b) for b in ra)
        assert abs((left_x+right_x)/2-BOARD_CENTER_X)<1
        assert min(b["y"] for b in la)==min(b["y"] for b in ra)
    assert len(groups)==layout["proof_chain"]["paired_stage_groups"]


def test_long_math_goes_to_own_line_even_if_next_item_is_short():
    from animation_engine.persistent_chalkboard import _proof_math_rows
    from animation_engine.classroom_policy import simple_classroom_policy
    from animation_engine.longboard_plan import LongboardPolicy
    from animation_engine.adaptive_layout import GlyphSize
    import animation_engine.persistent_chalkboard as boardmod
    selected=LongboardPolicy.parse(simple_classroom_policy())
    from animation_engine.longboard_plan import _sources
    _,_,execution,_,_,_,_=build_variant("A")
    sources=_sources(execution)
    def selective(tex,height):
        return GlyphSize(1030 if "frac" in tex else 130,42)
    size_cache={}
    placed,stop,rows=_proof_math_rows(
        ["m_goal","m_condition","m_definition"],
        sources,selected,selective,size_cache,148
    )
    assert rows==[["m_goal"],["m_condition","m_definition"]]
    assert stop>148
    assert all(block["scale"]>=selected.math_min_scale for block in placed)


def test_teacher_knowledge_and_distinct_cases_not_mixed_into_proof_stage_pairs():
    _,board,exe,cues,policy,manifest,units=build_variant("C")
    layout=make_chalkboard_plan(
        board,exe,cues,policy,measure=measure,proof_manifest=manifest
    )
    ids=["e_case_less","e_case_equal","e_case_greater",
         "e_knowledge_quadratic","e_final"]
    for event in layout["events"]:
        if event["event_id"] in ids:
            assert event["proof_layout"]["mode"] not in (
                "paired_left","paired_right"
            )
    assert all(event["proof_layout"]["source_order_preserved"]
               for event in layout["events"])


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
    bad["stages"][7]["cites"].remove("m_equal_result")
    bad["stages"][7]["carry_ids"].remove("m_equal_result")
    with pytest.raises(LongboardError,match="PROOF_INCOMPLETE_BRANCH_MERGE"):
        checked_proof_chain(bad,b,e)
    bad=copy.deepcopy(m)
    bad["stages"][5]["cites"].append("m_less_result")
    bad["stages"][5]["carry_ids"].append("m_less_result")
    with pytest.raises(LongboardError,match="PROOF_CASE_CROSS_REFERENCE"):
        checked_proof_chain(bad,b,e)


def test_wrong_mathematics_source_ids_or_skipped_stage_are_rejected():
    _,b,e,c,p,m,_=build_variant("A")
    bad=copy.deepcopy(m)
    bad["stages"][4]["output_ids"].remove("m_successor_split")
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
    # Compact short-formula packing can correctly fit all tiny mock glyphs
    # on one screen; use deliberately taller *valid* measured glyphs to force
    # a genuine full-board cut and exercise the no-unsafe-break invariant.
    taller=lambda tex,height:GlyphSize(210,85)
    good=make_chalkboard_plan(
        b,e,c,p,measure=taller,proof_manifest=m
    )
    assert good["page_count"]>1
    bad=copy.deepcopy(m)
    for stage in bad["stages"]:
        stage["safe_break_after"]=False
    with pytest.raises(LongboardError,match="PROOF_NO_SAFE_BREAK"):
        make_chalkboard_plan(
            b,e,c,p,measure=taller,proof_manifest=bad
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
