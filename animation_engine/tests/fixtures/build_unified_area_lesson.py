"""An original teacher-reviewed V2.6.1 *integrated* area lesson.

Graph and formula interpretation first (genuine V2.5.4 right-side diagram),
then a full-width integral calculation (existing V2.5 classroom engine).
Both stages use the EXACT same question and reference solution, but distinct
frozen execution plans, proven handoff ids and unmodified math literals.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy
from animation_engine.unified_classroom_flow import canonical_sha, checked_flow
from build_diagram_classroom_lesson import (
    integral_region, unit, formula,
)


def _units_and_specs():
    problem,kind,diagram,full_units,full_stages,regions=integral_region()
    # Existing V2.5.4 area lesson source is teacher reviewed and mathematically
    # correct. Its final evaluation will now live in the separate calculation
    # engine, without altering or fabricating the graph sources.
    graph_units = full_units[:5]
    graph_stages = [dict(x) for x in full_stages[:5]]
    graph_stages[-1]["reveal_ids"] = ["x_tip","y_tip"]
    # One unique question and one complete teacher-authored reference.
    reference = "\n".join(
        [problem] + [m["latex"] for u in full_units
                     for m in u["math"]] + [
            r"S=\int_0^1(x-x^2)\,dx",
            r"S=\int_0^1x\,dx-\int_0^1x^2\,dx",
            r"S=\left[\frac{x^2}{2}\right]_0^1-"
            r"\left[\frac{x^3}{3}\right]_0^1",
            r"S=\frac12-\frac13=\frac16",
        ]
    )
    handoff_tex = next(
        m["latex"] for u in graph_units for m in u["math"]
        if m["id"] == "area_step"
    )
    calculation_units = [
        unit("carry","承接图形得出的积分式",
             "回顾上函数减下函数建立的积分，继续完整计算。",
             [formula("area_handoff",handoff_tex,
                      "与前一阶段已经写出的积分式完全一致。")],
             phase="application"),
        unit("split","将积分分成两项",
             "利用积分的线性性质分别计算，不省略必要步骤。",
             [formula("area_split",
                     r"S=\int_0^1x\,dx-\int_0^1x^2\,dx",
                     "分项计算为初等积分。")]),
        unit("primitive","分别计算两项原函数",
             "按幂函数积分公式，保留上下限再进行代入。",
             [formula("area_primitive",
                     r"S=\left[\frac{x^2}{2}\right]_0^1-"
                     r"\left[\frac{x^3}{3}\right]_0^1",
                     "正确使用上下限计算。")]),
        unit("final","计算并归纳面积结果",
             "面积等于两个正数的差，最终结果为正。",
             [formula("area_evaluated",
                     r"S=\frac12-\frac13=\frac16",
                     "将上下限值依次代入后得到准确面积。")],
             phase="summary"),
    ]
    # Do not silently miscategorize procedure narration as 'knowledge':
    # the general area formula has its own genuine MathTex source on graph.
    assert [u["phase"] for u in graph_units].count("knowledge")==1
    assert all(u["phase"]!="knowledge" for u in calculation_units)
    return problem,reference,kind,diagram,graph_units,graph_stages,regions,calculation_units


def _export_stage(folder,*,package,board,execution,cues,policy,
                  extra=None,units=None,knowledge=None):
    folder.mkdir(parents=True,exist_ok=True)
    files = {
        "teaching_package.json": package,
        "storyboard.json": board.model_dump(mode="json"),
        "execution.json": execution.model_dump(mode="json"),
        "teacher_approved_cues.json": cues,
        "page_policy.json": policy,
    }
    if extra:
        files.update(extra)
    if units is not None:
        files["teaching_units.json"] = {
            "schema_version":"1.0","units":units
        }
    if knowledge is not None:
        files["core_knowledge.json"] = knowledge
    for name,data in files.items():
        (folder/name).write_text(
            json.dumps(data,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8"
        )


def export_lesson(destination: Path) -> dict:
    dest=Path(destination)
    dest.mkdir(parents=True,exist_ok=True)
    problem,reference,kind,diagram,graph_units,reveals,regions,calc_units=(
        _units_and_specs()
    )
    formula_unit=next(u for u in graph_units if u["phase"]=="knowledge")
    knowledge = {
        "schema_version":"1.0","teacher_reviewed":True,
        "points":[{
            "event_id":"e_rule","topic_id":"area_between_curves",
            "title":formula_unit["heading"],"kind":"formula",
            "formulae":[{
                "object_id":"m_area_rule",
                "latex":formula_unit["math"][0]["latex"],
            }],
            "used_in":["e_integrate"],
        }],
    }
    graph_package,graph_board,graph_plan,graph_cues=compile_teaching_units(
        problem=problem,reference_solution=reference,
        units=graph_units,teacher_reviewed=True,
        diagram_specs=[diagram],knowledge_catalog=knowledge
    )
    graph_contract={
        "schema_version":"1.0","mode":"verified_diagram_classroom",
        "teacher_reviewed":True,"kind":kind,
        "source_storyboard_sha256":graph_plan.source_storyboard_sha256,
        "source_event_id":"e_intro","filled_regions":regions,"stages":reveals,
    }
    _export_stage(
        dest/"graph",package=graph_package,board=graph_board,
        execution=graph_plan,cues=graph_cues,
        policy=simple_classroom_policy(result_ids=("m_area_step",)),
        extra={"diagram_classroom.json":graph_contract},
        units=graph_units,knowledge=knowledge
    )
    calc_package,calc_board,calc_plan,calc_cues=compile_teaching_units(
        problem=problem,reference_solution=reference,
        units=calc_units,teacher_reviewed=True
    )
    _export_stage(
        dest/"calculation",package=calc_package,board=calc_board,
        execution=calc_plan,cues=calc_cues,policy=simple_classroom_policy(),
        units=calc_units
    )
    payload={
        "schema_version":"1.0","mode":"unified_classroom_flow",
        "teacher_reviewed":True,
        "lesson_id":"area_graph_to_integral",
        "problem":problem,
        "reference_solution_sha256":canonical_sha(reference),
        "stages":[
            {
                "stage_id":"graph_analysis","engine":"diagram",
                "directory":"graph",
                "package_sha256":graph_package["validated_content_sha256"],
                "source_storyboard_sha256":graph_plan.source_storyboard_sha256,
                "event_ids":[x.event_id for x in graph_board.scenes],
                "handoff":[],
            },
            {
                "stage_id":"integral_calculation","engine":"standard",
                "directory":"calculation",
                "package_sha256":calc_package["validated_content_sha256"],
                "source_storyboard_sha256":calc_plan.source_storyboard_sha256,
                "event_ids":[x.event_id for x in calc_board.scenes],
                "handoff":[{
                    "from_stage":"graph_analysis",
                    "from_object_id":"m_area_step",
                    "to_object_id":"m_area_handoff",
                }],
            },
        ]
    }
    location=dest/"unified_flow.json"
    location.write_text(
        json.dumps(payload,ensure_ascii=False,indent=2)+"\n",
        encoding="utf-8"
    )
    checked_flow(location)
    print("V2_6_1_REVIEWED_INTEGRATED_SOURCE",location,
          "stages",len(payload["stages"]),
          "graph_events",len(graph_board.scenes),
          "math_events",len(calc_board.scenes))
    return payload


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True,
                   help="Destination folder with unified_flow.json and both stages")
    args=p.parse_args()
    export_lesson(args.output)
