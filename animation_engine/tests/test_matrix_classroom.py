"""V2.5.2: genuine algebra-checked matrix classroom; no inferred transforms."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))

from build_matrix_classroom_lesson import build_variant
from animation_engine.matrix_steps import (
    checked_matrix_steps, matrix_latex, parse_expr, operation_latex
)
from animation_engine.persistent_chalkboard import (
    make_chalkboard_plan,BOARD_CENTER_X,BOARD_START_Y,BOARD_BOTTOM_Y,
    _ink_width
)
from animation_engine.longboard_plan import LongboardError
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.board_motion import overlaps


def measure(tex,height):
    return GlyphSize(210, 55)


@pytest.mark.parametrize("variant,kind,count,answer",[
    ("A","linear_system",7,r"\begin{aligned}x=1\\y=2\\z=3\end{aligned}"),
    ("B","inverse",2,r"A^{-1}=\begin{bmatrix}1&-1\\-1&2\end{bmatrix}"),
    ("C","determinant",1,"D=a-1")
])
def test_exact_matrix_steps_source_math_and_unshifted_ink(
        variant,kind,count,answer):
    pkg, board, execution, cues, policy, manifest, units, final=build_variant(variant)
    lesson=checked_matrix_steps(manifest,board,execution)
    assert lesson.kind==kind
    assert len(lesson.steps)==count
    assert manifest["final"]["answer"]==final==answer
    layout=make_chalkboard_plan(
        board,execution,cues,policy,measure=measure,matrix_manifest=manifest
    )
    assert layout["matrix_operations"]["arithmetically_verified"] is True
    assert layout["matrix_operations"]["operation_count"]==count
    assert layout["page_count"]>=2 if variant=="A" else layout["page_count"]>=1
    assert layout["alignment"]["mode"]=="each_unit_centered_with_header_near_top"
    assert all(page["first_ink_y"]<=layout["alignment"]["max_first_ink_y"]
               for page in layout["alignment"]["pages"])
    seen={}
    perpage={}
    for event in layout["events"]:
        if event["erase_before"]:
            seen={}
        new=[b for b in event["added_blocks"] if not b.get("carry")]
        assert new
        left=min(b["x"] for b in new)
        right=max(b["x"]+_ink_width(b) for b in new)
        assert abs((left+right)/2-BOARD_CENTER_X)<1.01
        if event["matrix_stage"]=="matrix_operation":
            trio=[b for b in new if b["kind"]=="math"]
            assert len(trio)==3
            step=lesson.for_event(event["event_id"])
            assert [b["block_id"] for b in trio]==[
                step.before_id,step.operation_id,step.after_id
            ]
            # Whole before/operation/after unit is atomic; not a crossfade.
            assert all(t["y"]>=layout["coordinates"]["start_y"] for t in trio)
        for block in event["added_blocks"]:
            assert block["block_id"] not in seen
            assert all(not overlaps(block,old,margin=0) for old in seen.values())
            assert block["y"]+block["h"]<=BOARD_BOTTOM_Y+.01
            seen[block["block_id"]]=block
            if block["kind"]=="math":
                assert block["fragments"]
                assert abs(block["fragments"][0]["x"]-block["x"])<.01
        assert list(seen)==event["visible_block_ids"]
        perpage.setdefault(event["page_index"],[]).extend(event["added_blocks"])
    assert len(perpage)==layout["page_count"]
    assert set(layout["math_written_ids"])=={
        m["math_object_id"] for m in pkg["lesson"]["math_objects"]
    }


@pytest.mark.parametrize("variant",["A","B","C"])
def test_mutated_final_result_is_explicitly_blocked(variant):
    _,b,e,c,p,m,_,_=build_variant(variant)
    broken=copy.deepcopy(m)
    broken["final"]["answer"]="D=999"
    with pytest.raises(LongboardError,match="MATRIX_FINAL_ANSWER_MISMATCH"):
        checked_matrix_steps(broken,b,e)


def test_one_wrong_derived_matrix_entry_is_rejected():
    _,b,e,c,p,m,_,_=build_variant("A")
    bad=copy.deepcopy(m)
    bad["steps"][0]["after"][1][1]="987"
    with pytest.raises(LongboardError,match="MATRIX_AFTER_TEX_MISMATCH|MATRIX_FALSE_ROW_TRANSFORMATION"):
        checked_matrix_steps(bad,b,e)


def test_unreviewed_false_operation_and_mutated_provenance_are_rejected():
    _,b,e,c,p,m,_,_=build_variant("B")
    bad=copy.deepcopy(m)
    bad["teacher_reviewed"]=False
    with pytest.raises(LongboardError,match="MATRIX_INVALID_MANIFEST"):
        checked_matrix_steps(bad,b,e)
    bad=copy.deepcopy(m)
    bad["source_storyboard_sha256"]="0"*64
    with pytest.raises(LongboardError,match="MATRIX_SOURCE_HASH"):
        checked_matrix_steps(bad,b,e)
    bad=copy.deepcopy(m)
    bad["steps"][0]["operation"]["factor"]="-2"
    with pytest.raises(LongboardError,match="MATRIX_OPERATION_TEX_MISMATCH"):
        checked_matrix_steps(bad,b,e)


def test_matrix_requires_a_specialized_contract_and_cannot_be_silently_rendered():
    _,b,e,c,p,m,_,_=build_variant("A")
    with pytest.raises(LongboardError,match="CHALKBOARD_UNSUPPORTED_SPECIAL_LAYOUT"):
        make_chalkboard_plan(b,e,c,p,measure=measure)
    bad=copy.deepcopy(m)
    bad["steps"][0]["before"][0][0]="99"
    with pytest.raises(LongboardError,match="MATRIX_BEFORE_STATE_MISMATCH"):
        make_chalkboard_plan(b,e,c,p,measure=measure,matrix_manifest=bad)


@pytest.mark.parametrize("value", [
    "__import__('os').system('echo unsafe')",
    "a.__class__", "a[0]", "1/0", "x**100",
])
def test_expression_parser_blocks_unsafe_code(value):
    with pytest.raises(LongboardError):
        parse_expr(value)


def test_symbolic_division_requires_explicit_nonzero_assumption():
    import sympy as s
    from animation_engine.matrix_steps import _apply, _matrix
    m=_matrix([["1","0"],["0","a-1"]])
    op={"kind":"scale_row","target":2,"factor":"1/(a-1)"}
    with pytest.raises(LongboardError,match="MATRIX_UNPROVEN_NONZERO_DENOMINATOR"):
        _apply(m,op,[])
    assert _apply(m,op,["a-1"])==s.eye(2)


def test_matrix_operation_tex_is_canonical_and_mathtex_safe():
    assert operation_latex({
        "kind":"add_scaled_row","target":2,"source":1,"factor":"-2"
    })==r"R_{2}\leftarrow R_{2}-(2)R_{1}"
    assert matrix_latex([["1","2"],["3","4"]])==(
        r"\begin{bmatrix}1&2\\3&4\end{bmatrix}"
    )


def test_invalid_carry_modes_are_rejected_instead_of_losing_steps():
    _,b,e,c,p,m,_,_=build_variant("A")
    other={
        "schema_version":"1.0","mode":"multi_part_computation",
        "teacher_reviewed":True,
    }
    with pytest.raises(LongboardError,match="CHALKBOARD_MULTIPLE_SPECIAL_CONTRACTS"):
        make_chalkboard_plan(
            b,e,c,p,measure=measure,matrix_manifest=m,
            computation_manifest=other
        )
