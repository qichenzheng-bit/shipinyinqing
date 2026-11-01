"""V2.6.3 source-verified three-case proof plus a later summary stage.

Exercises explicit exhaustive alternatives and a theorem-backed merge without
moving a conclusion out of its conditional branch.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy
from animation_engine.unified_classroom_flow import canonical_sha, checked_flow
from build_proof_classroom_lesson import parameter_cases, _knowledge_catalog, unit, math
from build_unified_area_lesson import _export_stage
from animation_engine.classroom_math_memory import GLOBAL_SCOPE


def export_memory_parameter_cases(destination: Path) -> dict:
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    problem, proof_units, proof_stages, groups = parameter_cases()
    summary_units = [
        unit("carry", "承接完整分类讨论的结论",
             "三种情况已经合并，本幕引用已经证明的参数范围。",
             "只承接已完成的分类结论，不重新展开前面证明。",
             [math("final_recall", r"-1\leq a\leq1",
                   "直接使用已审核的最终参数范围。")],
             phase="application",event_type="calculation"),
        unit("interval", "改写为区间记法",
             "把两端点均包含的不等式改写成闭区间表示。",
             "检查两个端点没有遗漏。",
             [math("closed_interval", r"a\in[-1,1]",
                   "与前面得到的不等式完全等价。")],
             phase="summary",event_type="calculation"),
    ]
    reference="\n".join(
        [problem]+[m["latex"] for units in (proof_units, summary_units)
                   for item in units for m in item["math"]]
    )
    proof_pack,proof_board,proof_plan,proof_cues=compile_teaching_units(
        problem=problem,reference_solution=reference,units=proof_units,
        teacher_reviewed=True,knowledge_catalog=_knowledge_catalog("C",proof_units),
    )
    proof_contract={
        "schema_version":"1.0","mode":"verified_proof_chain",
        "teacher_reviewed":True,
        "source_storyboard_sha256":proof_plan.source_storyboard_sha256,
        "anchors":{"condition_object_id":"m_condition","goal_object_id":"m_goal"},
        "stages":proof_stages,"branch_groups":groups,
    }
    _export_stage(
        root/"proof",package=proof_pack,board=proof_board,execution=proof_plan,
        cues=proof_cues,policy=simple_classroom_policy(),
        extra={"proof_chain.json":proof_contract},units=proof_units,
        knowledge=_knowledge_catalog("C",proof_units),
    )
    last_pack,last_board,last_plan,last_cues=compile_teaching_units(
        problem=problem,reference_solution=reference,units=summary_units,
        teacher_reviewed=True,
    )
    _export_stage(
        root/"summary",package=last_pack,board=last_board,execution=last_plan,
        cues=last_cues,policy=simple_classroom_policy(),units=summary_units,
    )
    flow={
        "schema_version":"1.0","mode":"unified_classroom_flow",
        "teacher_reviewed":True,
        "lesson_id":"parameter_case_memory",
        "problem":problem,
        "reference_solution_sha256":canonical_sha(reference),
        "stages":[{
            "stage_id":"parameter_proof","engine":"proof",
            "directory":"proof",
            "package_sha256":proof_pack["validated_content_sha256"],
            "source_storyboard_sha256":proof_plan.source_storyboard_sha256,
            "event_ids":[e.event_id for e in proof_board.scenes],
            "handoff":[],
        },{
            "stage_id":"range_summary","engine":"standard",
            "directory":"summary",
            "package_sha256":last_pack["validated_content_sha256"],
            "source_storyboard_sha256":last_plan.source_storyboard_sha256,
            "event_ids":[e.event_id for e in last_board.scenes],
            "handoff":[{
                "from_stage":"parameter_proof",
                "from_object_id":"m_final",
                "to_object_id":"m_final_recall",
            }]
        }]
    }
    (root/"unified_flow.json").write_text(
        json.dumps(flow,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",
    )
    original=checked_flow(root/"unified_flow.json")
    def fact(fid,event,obj,scope,status="established"):
        return {
            "fact_id":fid,"stage_id":"parameter_proof","event_id":event,
            "object_id":obj,"status":status,"scope":scope,
        }
    def case(group,ident):
        return {"kind":"case","case_group":group,"case_id":ident}
    memory={
        "schema_version":"1.0","mode":"verified_classroom_memory",
        "teacher_reviewed":True,
        "source_flow_sha256":original.source_sha256,
        "facts":[
            fact("case_less_result","e_case_less","m_less_result",
                 case("parameter_sign","less")),
            fact("case_equal_result","e_case_equal","m_equal_result",
                 case("parameter_sign","equal")),
            fact("case_greater_result","e_case_greater","m_greater_result",
                 case("parameter_sign","greater")),
            fact("merged_cases","e_merge","m_merge",dict(GLOBAL_SCOPE)),
            fact("final_range","e_final","m_final",dict(GLOBAL_SCOPE)),
        ],
        "recalls":[{
            "recall_id":"summarize_range",
            "fact_id":"final_range",
            "stage_id":"range_summary","event_id":"e_carry",
            "to_object_id":"m_final_recall","mode":"restate",
            "active_scope":dict(GLOBAL_SCOPE),
        }],
        "case_merges":[{
            "merge_id":"exhaustive_parameter_cases",
            "stage_id":"parameter_proof","event_id":"e_merge",
            "to_object_id":"m_merge",
            "case_group":"parameter_sign",
            "case_fact_ids":[
                "case_less_result","case_equal_result","case_greater_result",
            ],
        }],
    }
    (root/"math_memory.json").write_text(
        json.dumps(memory,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",
    )
    return memory


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    source=export_memory_parameter_cases(args.output)
    print("V2_6_3_PARAMETER_CASES",len(source["facts"]),len(source["case_merges"]))
