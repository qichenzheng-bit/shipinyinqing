"""Reject single-formula pseudo-lessons and verify fully worked ODE unit flow."""
import copy
import sys
from pathlib import Path

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent/"fixtures"))

from build_complete_ode_lesson import build_new,UNITS,PROBLEM,REFERENCE_SOLUTION
from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.persistent_chalkboard import make_chalkboard_plan
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.longboard_plan import LongboardError
from animation_engine.board_motion import overlaps


def measure(latex,height):
    return GlyphSize(220,42)


def test_four_pedagogical_goals_not_eleven_isolated_formula_events():
    package,board,execution,cues,policy=build_new()
    assert len(board.scenes)==len(execution.scenes)==len(cues["events"])==4
    assert [len(u["math"]) for u in UNITS]==[1,4,3,3]
    assert len(package["lesson"]["math_objects"])==11
    assert [sum(a.kind=="progressive_write" for a in scene.actions)
            for scene in board.scenes]==[1,4,3,3]
    assert len(board.scenes[1].actions)==4
    assert "m_linear" not in [m["math_object_id"] for m in package["lesson"]["math_objects"]]
    assert board.scenes[1].event_id=="e_derive"
    assert board.scenes[1].actions[1].latex==r"(ye^{x^2})'=e^{x^2}y'+2xe^{x^2}y"
    assert cues["events"][1]["source_step_ids"]==["s2_1","s2_2","s2_3","s2_4"]
    assert cues["source_storyboard_sha256"]==execution.source_storyboard_sha256


def test_display_never_splits_product_rule_unit_across_erasures():
    _,board,execution,cues,policy=build_new()
    layout=make_chalkboard_plan(board,execution,cues,policy,measure=measure)
    assert layout["event_count"]==4
    assert set(layout["math_written_ids"])=={
        "m_"+step["id"] for u in UNITS for step in u["math"]
    }
    group=next(e for e in layout["events"] if e["event_id"]=="e_derive")
    assert [b["block_id"] for b in group["added_blocks"] if
            b["kind"]=="math" and not b.get("carry")]==[
        "m_multiply","m_product_rule","m_combined","m_integrated"
    ]
    initial=next(e for e in layout["events"] if e["event_id"]=="e_initial")
    if initial["erase_before"]:
        assert any(b["block_id"]=="m_integrated" and b.get("carry")
                   for b in initial["added_blocks"])
    assert layout["events"][1]["math_write_count"]==4
    assert len({b["block_id"] for b in group["added_blocks"]})==len(
        group["added_blocks"]
    )
    # Erasing before a whole unit is legitimate; inside it is forbidden.
    previous={}
    for row in layout["events"]:
        if row["erase_before"]: previous={}
        for b in row["added_blocks"]:
            assert b["block_id"] not in previous
            assert not any(overlaps(b,old,0) for old in previous.values())
            previous[b["block_id"]]=b
        assert list(previous)==row["visible_block_ids"]


def test_no_boilerplate_nonessential_fragments_while_derivation_is_complete():
    _,board,execution,cues,_=build_new()
    assert len(cues["events"])<len(
        [action for scene in execution.scenes for action in scene.actions]
    )
    texts=[u["math"] for u in UNITS]
    assert any("e^{x^2}y'+2xe^{x^2}y" in x["latex"] for x in texts[1])
    assert any("=e^{x^2}+C" in x["latex"] for x in texts[1])
    assert any("C=-1" in x["latex"] for x in texts[2])
    assert any("y'+2xy=" in x["latex"] for x in texts[3])
    assert any("y(0)=" in x["latex"] for x in texts[3])


def test_reject_absent_reasons_and_pointless_knowledge_one_line():
    bad=copy.deepcopy(UNITS)
    bad[1]["math"][1]["reason"]=""
    with pytest.raises(LongboardError,match="REASON_MISSING"):
        compile_teaching_units(problem=PROBLEM,reference_solution=REFERENCE_SOLUTION,
                               units=bad,teacher_reviewed=True)
    bad=copy.deepcopy(UNITS)
    bad[1]["math"]=[]
    with pytest.raises(LongboardError,match="MATH_COVERAGE"):
        compile_teaching_units(problem=PROBLEM,reference_solution=REFERENCE_SOLUTION,
                               units=bad,teacher_reviewed=True)
    # One genuinely useful mathematical fact may deserve its own moment:
    # never force the author to invent another line only to pass a count rule.
    one_line=copy.deepcopy(UNITS)
    one_line[1]["math"]=one_line[1]["math"][:1]
    compile_teaching_units(problem=PROBLEM,reference_solution=REFERENCE_SOLUTION,
                           units=one_line,teacher_reviewed=True)


def test_reject_modified_source_or_oversized_math_instead_of_truncating():
    package,board,execution,cues,policy=build_new()
    altered=copy.deepcopy(cues)
    altered["source_storyboard_sha256"]="0"*64
    with pytest.raises(LongboardError,match="SOURCE_HASH"):
        make_chalkboard_plan(board,execution,altered,policy,measure=measure)
    with pytest.raises(LongboardError):
        make_chalkboard_plan(board,execution,cues,policy,
                             measure=lambda latex,height:GlyphSize(10000,40))


def test_unreviewed_math_is_never_marked_ready_just_because_latex_is_valid():
    # This is a real regression case: 1=2 is syntactically valid MathTex,
    # and hashes authenticate bytes, not mathematical truth.
    import copy
    wrong=copy.deepcopy(UNITS)
    wrong[0]["math"][0]["latex"]="1=2"
    with pytest.raises(LongboardError,match="EXPLICIT_TEACHER_REVIEW"):
        compile_teaching_units(
            problem=PROBLEM,reference_solution=REFERENCE_SOLUTION,
            units=wrong
        )


def test_diagram_source_is_rejected_instead_of_silently_omitted_from_movie():
    from visual_director.models import (
        DirectorOptions,DiagramSpec,DiagramPoint,DiagramLine
    )
    from visual_director.director import build_storyboard
    from animation_engine.planner import build_execution_plan
    pkg,board,execution,cues,policy=build_new()
    diagram=DiagramSpec(
        event_id="e_method",
        points=[
            DiagramPoint(id="A",x=.10,y=.20),
            DiagramPoint(id="B",x=.60,y=.70),
        ],
        lines=[DiagramLine(id="segment",start="A",end="B")],
    )
    board2=build_storyboard(pkg,DirectorOptions(diagrams=[diagram]))
    assert board2.scenes[0].diagram is not None
    exec2=build_execution_plan(board2)
    cue2=dict(cues,source_storyboard_sha256=exec2.source_storyboard_sha256)
    with pytest.raises(LongboardError,match="UNSUPPORTED_SPECIAL_LAYOUT"):
        make_chalkboard_plan(board2,exec2,cue2,policy,measure=measure)


def test_default_cli_rejects_unsupported_diagram_without_explicit_policy(
        tmp_path,capsys):
    import json
    from visual_director.models import (
        DirectorOptions,DiagramSpec,DiagramPoint,DiagramLine
    )
    from visual_director.director import build_storyboard
    from animation_engine.planner import build_execution_plan
    from animation_engine.cli import main
    package,_,_,cues,_=build_new()
    diagram=DiagramSpec(
        event_id="e_method",
        points=[
            DiagramPoint(id="A",x=.15,y=.25),
            DiagramPoint(id="B",x=.55,y=.65),
        ],
        lines=[DiagramLine(id="segment",start="A",end="B")],
    )
    board=build_storyboard(package,DirectorOptions(diagrams=[diagram]))
    execution=build_execution_plan(board)
    cues=dict(cues,source_storyboard_sha256=execution.source_storyboard_sha256)
    for name,content in {
        "board.json":board.model_dump(mode="json"),
        "execution.json":execution.model_dump(mode="json"),
        "cues.json":cues,
    }.items():
        (tmp_path/name).write_text(
            json.dumps(content,ensure_ascii=False),encoding="utf-8"
        )
    rc=main([
        "plan-longboard",
        "--storyboard",str(tmp_path/"board.json"),
        "--execution",str(tmp_path/"execution.json"),
        "--classroom-cues",str(tmp_path/"cues.json"),
        "--output",str(tmp_path/"layout.json")
    ])
    assert rc==2
    assert "SPECIAL_LAYOUT_REQUIRES_EXPLICIT_POLICY" in capsys.readouterr().err
    assert not (tmp_path/"layout.json").exists()
