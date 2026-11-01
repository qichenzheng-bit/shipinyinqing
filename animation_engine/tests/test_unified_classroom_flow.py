"""V2.6.1 shared-question flow: real source contracts, safe handoff, stages."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
import sympy as sp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from build_unified_area_lesson import export_lesson
from animation_engine.unified_classroom_flow import (
    canonical_sha, checked_flow, plan_flow
)
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.longboard_plan import LongboardError


def measures(tex,height):
    return GlyphSize(185,42)


@pytest.fixture
def project(tmp_path):
    root=tmp_path/"integrated"
    export_lesson(root)
    return root


def read(root):
    return json.loads((root/"unified_flow.json").read_text(encoding="utf-8"))


def write(root,value):
    (root/"unified_flow.json").write_text(
        json.dumps(value,ensure_ascii=False,indent=2)+"\n",
        encoding="utf-8"
    )


def test_integrated_reviewed_lesson_plan_preserves_v25_modes_and_event_order(project):
    flow=checked_flow(project/"unified_flow.json")
    plan=plan_flow(project/"unified_flow.json",measure=measures)
    assert flow.lesson_id=="area_graph_to_integral"
    assert [x.engine for x in flow.stages]==["diagram","standard"]
    assert plan["stage_count"]==2
    assert plan["event_count"]==9
    assert plan["page_count"]>=2
    assert plan["fixed_header"]
    assert plan["mode_change_policy"]=="explicit_full_board_wipe"
    assert len({x["global_event_id"] for x in plan["events"]})==9
    assert [x["stage_id"] for x in plan["stages"]]==[
        "graph_analysis","integral_calculation"
    ]
    assert plan["stages"][0]["layout_mode"]=="diagram_left_math_right_geometry"
    assert plan["stages"][1]["layout_mode"]=="each_unit_centered_with_header_near_top"
    assert plan["stages"][1]["transition"]=="full_board_erase_with_fixed_header"
    assert plan["stages"][1]["handoff"]==[{
        "from_stage":"graph_analysis",
        "from_object_id":"m_area_step",
        "to_object_id":"m_area_handoff"
    }]
    assert plan["events"][0]["global_event_id"]=="graph_analysis:e_intro"
    assert plan["events"][5]["global_event_id"]=="integral_calculation:e_carry"
    assert plan["events"][-1]["global_event_id"]=="integral_calculation:e_final"


def test_flow_does_not_fabricate_a_new_area_integral(project):
    flow=checked_flow(project/"unified_flow.json")
    from animation_engine.longboard_plan import _sources
    from animation_engine.models import ExecutionPlan
    graph=_sources(ExecutionPlan.model_validate(flow.stages[0].execution))
    calculation=_sources(ExecutionPlan.model_validate(flow.stages[1].execution))
    assert graph["m_area_step"]["latex"]==calculation["m_area_handoff"]["latex"]
    assert calculation["m_area_handoff"]["latex"]==r"S=\int_0^1(x-x^2)\,dx"
    assert calculation["m_area_split"]["latex"]==(
        r"S=\int_0^1x\,dx-\int_0^1x^2\,dx"
    )
    assert calculation["m_area_evaluated"]["latex"]==(
        r"S=\frac12-\frac13=\frac16"
    )
    x=sp.symbols("x",real=True)
    assert sp.integrate(x-x*x,(x,0,1))==sp.Rational(1,6)
    assert canonical_sha(flow.stages[0].package["source"]["reference_solution"])==(
        canonical_sha(flow.stages[1].package["source"]["reference_solution"])
    )


@pytest.mark.parametrize("change,error",[
    ("reviewed","FLOW_INVALID_MANIFEST"),
    ("unknown_engine","FLOW_UNKNOWN_ENGINE"),
    ("bad_directory","FLOW_UNSAFE_DIRECTORY"),
    ("same_stage","FLOW_DUPLICATE_STAGE"),
    ("same_folder","FLOW_DUPLICATE_STAGE_DIRECTORY"),
    ("bad_sha","FLOW_STORYBOARD_HASH"),
    ("different_question","FLOW_NOT_SAME_APPROVED_QUESTION"),
    ("different_solution","FLOW_NOT_SAME_APPROVED_QUESTION"),
    ("missing_handoff","FLOW_MISSING_EXPLICIT_HANDOFF"),
    ("unknown_source","FLOW_HANDOFF_NOT_WRITTEN"),
    ("wrong_source","FLOW_HANDOFF_MATH_MUTATION"),
    ("future_target","FLOW_HANDOFF_NOT_WRITTEN"),
    ("nonadjacent","FLOW_HANDOFF_NONADJACENT"),
    ("duplicate_handoff","FLOW_DUPLICATE_HANDOFF"),
    ("fake_first_handoff","FLOW_FIRST_STAGE_CANNOT_HANDOFF"),
])
def test_flow_fails_closed_on_unreviewed_math_or_order(project,change,error):
    bad=read(project)
    a,b=bad["stages"]
    bridge=b["handoff"][0]
    if change=="reviewed": bad["teacher_reviewed"]=False
    elif change=="unknown_engine": b["engine"]="unsupported"
    elif change=="bad_directory": b["directory"]="../../main"
    elif change=="same_stage": b["stage_id"]=a["stage_id"]
    elif change=="same_folder": b["directory"]=a["directory"]
    elif change=="bad_sha": b["source_storyboard_sha256"]="0"*64
    elif change=="different_question": bad["problem"]="另一个无关的数学题"
    elif change=="different_solution": bad["reference_solution_sha256"]="0"*64
    elif change=="missing_handoff": b["handoff"]=[]
    elif change=="unknown_source": bridge["from_object_id"]="m_unproven"
    elif change=="wrong_source": bridge["from_object_id"]="m_area_rule"
    elif change=="future_target": bridge["to_object_id"]="m_area_evaluated"
    elif change=="nonadjacent": bridge["from_stage"]="other"
    elif change=="duplicate_handoff": b["handoff"].append(dict(bridge))
    elif change=="fake_first_handoff": a["handoff"]=[dict(bridge)]
    write(project,bad)
    with pytest.raises(LongboardError,match=error):
        checked_flow(project/"unified_flow.json")


def test_single_engine_source_flow_is_valid_without_fake_second_engine(project):
    payload=read(project)
    payload["stages"].pop()
    write(project,payload)
    verified=checked_flow(project/"unified_flow.json")
    assert len(verified.stages)==1
    assert verified.stages[0].engine=="diagram"


def test_source_package_mutation_must_be_rejected(project):
    stage=project/"calculation"/"teaching_package.json"
    p=json.loads(stage.read_text())
    p["source"]["reference_solution"]="made up"
    stage.write_text(json.dumps(p),encoding="utf-8")
    with pytest.raises(LongboardError,match="FLOW_PACKAGE_SOURCE_HASH"):
        checked_flow(project/"unified_flow.json")


def test_missing_math_engine_contract_must_fail_not_silently_draw(project):
    (project/"graph"/"diagram_classroom.json").unlink()
    with pytest.raises(LongboardError,match="FLOW_MISSING_FILE"):
        checked_flow(project/"unified_flow.json")


def test_multiple_engines_within_a_single_stage_are_rejected(project):
    (project/"graph"/"matrix_steps.json").write_text("{}")
    with pytest.raises(LongboardError,match="FLOW_ENGINE_MANIFEST_CONFLICT"):
        checked_flow(project/"unified_flow.json")


def test_teacher_knowledge_is_a_real_mathematical_rule(project):
    from animation_engine.core_knowledge import checked_core_knowledge
    raw=json.loads((project/"graph"/"teaching_units.json").read_text())
    catalog=json.loads((project/"graph"/"core_knowledge.json").read_text())
    checked_core_knowledge(raw["units"],catalog)
    assert catalog["points"][0]["formulae"][0]["latex"]==(
        r"S=\int_a^b\!\left[f(x)-g(x)\right]\,dx"
    )
    assert catalog["points"][0]["used_in"]==["e_integrate"]


def test_plan_source_digest_and_source_file_roundtrip(project):
    p=project/"unified_flow.json"
    a=plan_flow(p,measure=measures)
    b=plan_flow(p,measure=measures)
    assert a==b
    assert a["source_flow_sha256"]==canonical_sha(read(project))
    for stage in a["stages"]:
        assert stage["page_count"]>=1
    assert not any("audio" in e for e in a["events"])


def test_60fps_36_frame_wipe_is_valid_but_full_stage_cannot_be_short(monkeypatch):
    import subprocess
    from animation_engine.unified_classroom_flow import (
        _video_frames, TRANSITION_FRAMES
    )

    def fake_ffprobe(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 0,
            json.dumps({"streams":[{
                "width":1280,"height":720,
                "r_frame_rate":"60/1",
                "nb_read_frames":str(TRANSITION_FRAMES)
            }]}),
            ""
        )

    monkeypatch.setattr(subprocess, "run", fake_ffprobe)
    assert TRANSITION_FRAMES == 36
    assert _video_frames(Path("board_wipe.mp4"),60,
                         min_frames=TRANSITION_FRAMES)==36
    with pytest.raises(LongboardError,match="FLOW_VIDEO_TOO_SHORT"):
        _video_frames(Path("instruction_stage.mp4"),60)
