"""V2.6.3: prove classroom memory refers only to existing reviewed math.

No test pretends that source hashes alone prove mathematical correctness.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))

from build_math_memory_triangle import export_memory_triangle
from build_math_memory_cases import export_memory_parameter_cases
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.classroom_math_memory import (
    GLOBAL_SCOPE, checked_memory, plan_memory, render_memory,
)
from animation_engine.longboard_plan import LongboardError


def measure(latex, frame):
    return GlyphSize(160, 37)


def get(root):
    return json.loads((root/"math_memory.json").read_text(encoding="utf-8"))


def put(root, value):
    (root/"math_memory.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8",
    )


@pytest.fixture
def triangle(tmp_path):
    root=tmp_path/"triangle"
    export_memory_triangle(root)
    return root


@pytest.fixture
def parameter(tmp_path):
    root=tmp_path/"cases"
    export_memory_parameter_cases(root)
    return root


def test_three_stage_math_memory_uses_original_unchanged_formula(triangle):
    contract=checked_memory(triangle/"math_memory.json")
    assert [s.engine for s in contract.flow.stages] == [
        "diagram", "standard", "standard"
    ]
    assert len(contract.facts)==3
    assert len(contract.recalls)==4
    assert contract.recalls[2]["source_stage_id"]=="introduce_triangle"
    assert contract.recalls[2]["stage_id"]=="calculate_perimeter"
    assert contract.recalls[2]["source_latex"] == r"AB=8,\quad AC=6"
    assert contract.recalls[2]["target_latex"] == r"AB=8,\quad AC=6"
    assert contract.recalls[3]["is_literal_restatement"] is False
    assert contract.recalls[0]["source_latex"]==r"BC^2=8^2+6^2"
    assert contract.event_memory("calculate_perimeter","e_legs")["recalled"]==[
        "restore_original_legs"
    ]


def test_memory_plan_retains_real_rendered_math_layout_and_page_order(triangle):
    plan=plan_memory(triangle/"math_memory.json",measure=measure,adaptive=True)
    assert plan["memory_contract_validated"]
    assert plan["fixed_header"] and plan["event_count"]==11
    assert plan["stage_count"]==3
    assert plan["memory"]["recall_count"]==4
    assert plan["memory"]["mathematical_truth_status"]==(
        "teacher_reviewed_not_formally_proven"
    )
    assert plan["page_count"]==sum(s["page_count"] for s in plan["stages"])
    assert all(item["global_page_index"]>=1 for item in plan["events"])
    assert [s["diagram_action"] for s in plan["stages"]]==[
        "create","hold","hold"
    ]
    assert [s["layout_mode"] for s in plan["stages"]]==[
        "diagram_native", "math_left_diagram_right",
        "math_left_diagram_right",
    ]
    assert plan["events"][-1]["memory"]["recalled"]==[]
    assert next(x for x in plan["events"] if x["global_event_id"]==
                "calculate_perimeter:e_recap")["memory"]["recalled"]==[
        "carry_hypotenuse"
    ]


def test_memory_plan_also_works_without_adaptive_visual_layout(triangle):
    plan=plan_memory(triangle/"math_memory.json",measure=measure)
    assert plan["event_count"]==11
    assert plan["memory"]["fact_count"]==3
    assert plan["voice_status"]=="not_recorded"


@pytest.mark.parametrize("change,error",[
    ("unreviewed","MEMORY_INVALID_MANIFEST"),
    ("unknown_mode","MEMORY_INVALID_MANIFEST"),
    ("extra_root","MEMORY_INVALID_MANIFEST"),
    ("stale_flow","MEMORY_FLOW_SOURCE_MUTATION"),
    ("no_facts","MEMORY_FACT_COVERAGE"),
    ("duplicate_fact","MEMORY_DUPLICATE_OR_UNPROVED_FACT"),
    ("invalid_status","MEMORY_DUPLICATE_OR_UNPROVED_FACT"),
    ("missing_math_source","MEMORY_SOURCE_NOT_WRITTEN"),
    ("fake_fact_scene","MEMORY_SOURCE_NOT_WRITTEN"),
    ("bad_scope_fields","MEMORY_INVALID_SCOPE_FIELDS"),
    ("fake_case_fact","MEMORY_CASE_ORIGIN_NOT_PROVED"),
    ("duplicate_recall","MEMORY_DUPLICATE_RECALL"),
    ("unknown_fact","MEMORY_UNREGISTERED_FACT"),
    ("future_fact","MEMORY_PREMATURE_OR_SELF_CITATION"),
    ("wrong_target","MEMORY_RECALL_NOT_WRITTEN"),
    ("changed_restatement","MEMORY_RESTATEMENT_MATH_MUTATED"),
    ("bad_mode","MEMORY_RECALL_MODE"),
    ("invented_case_scope","MEMORY_ACTIVE_SCOPE_INVENTED"),
    ("wrong_recall_fields","MEMORY_RECALL_FIELDS"),
    ("case_merges_not_list","MEMORY_MERGE_COVERAGE"),
])
def test_memory_rejects_invalid_or_future_source(triangle,change,error):
    data=get(triangle)
    fact=data["facts"][0]
    recall=data["recalls"][0]
    if change=="unreviewed": data["teacher_reviewed"]=False
    elif change=="unknown_mode": data["mode"]="fabricated_memory"
    elif change=="extra_root": data["unknown"]=1
    elif change=="stale_flow": data["source_flow_sha256"]="f"*64
    elif change=="no_facts": data["facts"]=[]
    elif change=="duplicate_fact": data["facts"].append(copy.deepcopy(fact))
    elif change=="invalid_status": fact["status"]="unverified"
    elif change=="missing_math_source": fact["object_id"]="m_nonexistent"
    elif change=="fake_fact_scene": fact["event_id"]="e_wrong_event"
    elif change=="bad_scope_fields": fact["scope"]={"kind":"global"}
    elif change=="fake_case_fact":
        fact["scope"]={"kind":"case","case_group":"fake","case_id":"one"}
    elif change=="duplicate_recall":
        data["recalls"].append(copy.deepcopy(recall))
    elif change=="unknown_fact": recall["fact_id"]="never_existed"
    elif change=="future_fact":
        recall.update({
            "fact_id":"computed_hypotenuse","stage_id":"introduce_triangle",
            "event_id":"e_apply","to_object_id":"m_square",
            "active_scope":dict(GLOBAL_SCOPE),
        })
    elif change=="wrong_target": recall["to_object_id"]="m_not_written"
    elif change=="changed_restatement":
        recall.update({
            "stage_id":"calculate_perimeter","event_id":"e_perimeter",
            "to_object_id":"m_perimeter_rule",
        })
    elif change=="bad_mode": recall["mode"]="guess"
    elif change=="invented_case_scope":
        recall["active_scope"]={
            "kind":"case","case_group":"parameter_sign","case_id":"less"
        }
    elif change=="wrong_recall_fields": recall["extra"]="disallowed"
    elif change=="case_merges_not_list": data["case_merges"]={}
    put(triangle,data)
    with pytest.raises(LongboardError,match=error):
        checked_memory(triangle/"math_memory.json")


def test_parameter_proof_case_merge_verifies_every_real_branch(parameter):
    contract=checked_memory(parameter/"math_memory.json")
    assert [s.engine for s in contract.flow.stages]==["proof","standard"]
    assert len(contract.facts)==5
    assert len(contract.merges)==1
    assert contract.merges[0]["case_coverage_verified"]
    assert contract.merges[0]["covered_cases"]==["equal","greater","less"]
    assert contract.recalls[0]["source_latex"]==r"-1\leq a\leq1"
    assert contract.recalls[0]["target_latex"]==r"-1\leq a\leq1"
    planned=plan_memory(parameter/"math_memory.json",measure=measure)
    assert planned["memory"]["case_merge_count"]==1
    assert next(x for x in planned["events"]
                if x["global_event_id"]=="parameter_proof:e_merge"
               )["memory"]["merged"]==["exhaustive_parameter_cases"]


@pytest.mark.parametrize("change,error",[
    ("goal_as_fact","MEMORY_GOAL_NOT_ESTABLISHED"),
    ("case_as_global","MEMORY_CASE_FACT_CANNOT_BE_GLOBAL"),
    ("wrong_case_id","MEMORY_CASE_ORIGIN_NOT_PROVED"),
    ("case_leaks_to_summary","MEMORY_CASE_SCOPE_LEAK"),
    ("case_skip","MEMORY_INCOMPLETE_CASE_COVERAGE"),
    ("case_duplicate","MEMORY_MERGE_BAD_COVERAGE"),
    ("merge_wrong_event","MEMORY_MERGE_NOT_A_PROOF_MERGE"),
    ("unknown_group","MEMORY_MERGE_PREMATURE_OR_WRONG_CASE"),
])
def test_proof_case_branch_conditions_cannot_leak(parameter,change,error):
    data=get(parameter)
    if change=="goal_as_fact":
        data["facts"].append({
            "fact_id":"unproven_goal","stage_id":"parameter_proof",
            "event_id":"e_setup","object_id":"m_goal",
            "status":"established","scope":dict(GLOBAL_SCOPE),
        })
    elif change=="case_as_global":
        data["facts"][0]["scope"]=dict(GLOBAL_SCOPE)
    elif change=="wrong_case_id":
        data["facts"][0]["scope"]["case_id"]="equal"
    elif change=="case_leaks_to_summary":
        data["recalls"][0]["fact_id"]="case_less_result"
    elif change=="case_skip":
        data["case_merges"][0]["case_fact_ids"].pop()
    elif change=="case_duplicate":
        data["case_merges"][0]["case_fact_ids"].append("case_less_result")
    elif change=="merge_wrong_event":
        data["case_merges"][0]["event_id"]="e_final"
        data["case_merges"][0]["to_object_id"]="m_final"
    elif change=="unknown_group":
        data["case_merges"][0]["case_group"]="unrelated"
    put(parameter,data)
    with pytest.raises(LongboardError,match=error):
        checked_memory(parameter/"math_memory.json")


def test_memory_render_validation_precedes_any_rendering(triangle,tmp_path):
    data=get(triangle)
    data["source_flow_sha256"]="0"*64
    put(triangle,data)
    with pytest.raises(LongboardError,match="MEMORY_FLOW_SOURCE_MUTATION"):
        render_memory(
            triangle/"math_memory.json",
            output_mp4=tmp_path/"out.mp4",
            output_json=tmp_path/"out.json",
            adaptive=True,
        )
