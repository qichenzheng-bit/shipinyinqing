"""V2.6.3 original 6-8-10 triangle: graph -> computation -> cross-stage recall.

Single teacher-approved source, authentic source-bound Manim diagram and
MathTex formulas. A non-adjacent reminder of the given sides is essential
to the perimeter calculation; the triangle remains visible throughout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy
from animation_engine.unified_classroom_flow import canonical_sha, checked_flow
from build_diagram_classroom_lesson import geometry_proof, formula, unit
from build_unified_area_lesson import _export_stage


def export_memory_triangle(destination: Path) -> dict:
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    _, kind, geom, _, source_stages, _ = geometry_proof()
    problem = (
        r"求直角三角形的斜边与周长：\quad AB=8,\ AC=6,\ \angle A=90^\circ"
    )
    graph_units = [
        unit("intro", "明确直角边与图像",
             "从题设确定直角顶点，以及两条直角边的长度。",
             [formula("legs", r"AB=8,\quad AC=6", "题目已知的两直角边。")],
             phase="strategy"),
        unit("angle", "确定直角与斜边",
             "题设直角位于顶点处，另外两个顶点之间的线段是斜边。",
             [formula("perpendicular", r"AB\perp AC", "题设确定垂直关系。")]),
        unit("rule", "勾股定理",
             "直角三角形中两直角边的平方和等于斜边平方。",
             [formula("pythagoras", r"a^2+b^2=c^2",
                      "勾股定理适用于这道直角三角形题。")],
             phase="knowledge"),
        unit("apply", "把题目数据代入定理",
             "根据图中斜边位置和两直角边，建立计算式。",
             [formula("square", r"BC^2=8^2+6^2",
                      "由勾股定理准确代入两直角边。")],
             phase="application"),
    ]
    calculation_units = [
        unit("carry", "承接已经建立的关系",
             "继续求解上一幕通过勾股定理得到的斜边平方。",
             [formula("square_handoff", r"BC^2=8^2+6^2",
                      "与上一幕公式逐字一致。")],
             phase="application"),
        unit("square_value", "分别计算两个平方",
             "把八和六分别平方，再进行加法计算。",
             [formula("squares", r"BC^2=64+36=100",
                      "保持斜边平方的准确表达。")]),
        unit("hypotenuse", "得到斜边的长度",
             "长度取正值，由平方关系得到十。",
             [formula("hypotenuse", r"BC=10",
                      "三角形边长是非负数。")]),
    ]
    perimeter_units = [
        unit("recap", "引用上一幕的斜边结论",
             "斜边已经计算出来，本幕不重复求平方根。",
             [formula("hypotenuse_recall", r"BC=10",
                      "承接上一幕已经算出的斜边长度。")],
             phase="application"),
        unit("legs", "回顾题目给出的两直角边",
             "再次使用开始时确认的两个已知长度。",
             [formula("legs_recall", r"AB=8,\quad AC=6",
                      "与第一幕题目条件完全一致。")],
             phase="strategy"),
        unit("perimeter", "建立周长的加法关系",
             "三角形周长等于三条边长度的和。",
             [formula("perimeter_rule", r"P=AB+AC+BC",
                      "周长定义，使用三条边的长度。")]),
        unit("final", "代入并得到周长",
             "把两条直角边和斜边的已知数值相加。",
             [formula("perimeter_result", r"P=8+6+10=24",
                      "三边的长度之和为二十四。")],
             phase="summary"),
    ]
    reference = "\n".join(
        [problem] +
        [m["latex"] for units in (
            graph_units, calculation_units, perimeter_units
        ) for item in units for m in item["math"]]
    )
    knowledge = {
        "schema_version": "1.0", "teacher_reviewed": True,
        "points": [{
            "event_id": "e_rule",
            "topic_id": "pythagorean_theorem",
            "title": "勾股定理",
            "kind": "theorem",
            "formulae": [{
                "object_id": "m_pythagoras",
                "latex": r"a^2+b^2=c^2",
            }],
            "used_in": ["e_apply"],
        }],
    }
    stages = [dict(x) for x in source_stages[:4]]
    graph_pack, graph_board, graph_plan, graph_cues = compile_teaching_units(
        problem=problem, reference_solution=reference,
        units=graph_units, teacher_reviewed=True,
        knowledge_catalog=knowledge, diagram_specs=[geom],
    )
    diagram_contract = {
        "schema_version": "1.0", "mode": "verified_diagram_classroom",
        "teacher_reviewed": True, "kind": kind,
        "source_storyboard_sha256": graph_plan.source_storyboard_sha256,
        "source_event_id": "e_intro", "filled_regions": [], "stages": stages,
    }
    _export_stage(
        root / "diagram", package=graph_pack, board=graph_board,
        execution=graph_plan, cues=graph_cues,
        policy=simple_classroom_policy(),
        extra={"diagram_classroom.json": diagram_contract},
        units=graph_units, knowledge=knowledge,
    )
    calc_pack, calc_board, calc_plan, calc_cues = compile_teaching_units(
        problem=problem, reference_solution=reference,
        units=calculation_units, teacher_reviewed=True,
    )
    _export_stage(
        root/"hypotenuse", package=calc_pack, board=calc_board,
        execution=calc_plan, cues=calc_cues,
        policy=simple_classroom_policy(), units=calculation_units,
    )
    p_pack, p_board, p_plan, p_cues = compile_teaching_units(
        problem=problem, reference_solution=reference,
        units=perimeter_units, teacher_reviewed=True,
    )
    _export_stage(
        root/"perimeter", package=p_pack, board=p_board,
        execution=p_plan, cues=p_cues,
        policy=simple_classroom_policy(), units=perimeter_units,
    )
    flow = {
        "schema_version": "1.0",
        "mode": "unified_classroom_flow",
        "teacher_reviewed": True,
        "lesson_id": "triangle_pythagoras_perimeter_memory",
        "problem": problem,
        "reference_solution_sha256": canonical_sha(reference),
        "stages": [
            {
                "stage_id": "introduce_triangle", "engine": "diagram",
                "directory": "diagram",
                "package_sha256": graph_pack["validated_content_sha256"],
                "source_storyboard_sha256": graph_plan.source_storyboard_sha256,
                "event_ids": [x.event_id for x in graph_board.scenes],
                "handoff": [],
            }, {
                "stage_id": "calculate_hypotenuse", "engine": "standard",
                "directory": "hypotenuse",
                "package_sha256": calc_pack["validated_content_sha256"],
                "source_storyboard_sha256": calc_plan.source_storyboard_sha256,
                "event_ids": [x.event_id for x in calc_board.scenes],
                "handoff": [{
                    "from_stage": "introduce_triangle",
                    "from_object_id": "m_square",
                    "to_object_id": "m_square_handoff",
                }],
            }, {
                "stage_id": "calculate_perimeter", "engine": "standard",
                "directory": "perimeter",
                "package_sha256": p_pack["validated_content_sha256"],
                "source_storyboard_sha256": p_plan.source_storyboard_sha256,
                "event_ids": [x.event_id for x in p_board.scenes],
                "handoff": [{
                    "from_stage": "calculate_hypotenuse",
                    "from_object_id": "m_hypotenuse",
                    "to_object_id": "m_hypotenuse_recall",
                }],
            }
        ],
    }
    (root/"unified_flow.json").write_text(
        json.dumps(flow, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8",
    )
    verified = checked_flow(root/"unified_flow.json")
    adaptive = {
        "schema_version": "1.0",
        "mode": "adaptive_classroom_layout",
        "teacher_reviewed": True,
        "source_flow_sha256": verified.source_sha256,
        "stages": [{
            "stage_id": sid,
            "layout": "diagram_native" if i == 0 else "math_left_diagram_right",
            "diagram_action": "create" if i == 0 else "hold",
            "diagram_source_stage": "introduce_triangle",
            "teaching_reason": (
                "展示题目直角三角形与两条已知直角边" if i == 0 else
                "后续计算始终依赖已绘制的三角形图，跨幕保留"
            ),
        } for i,sid in enumerate([
            "introduce_triangle", "calculate_hypotenuse", "calculate_perimeter"
        ])],
    }
    (root/"adaptive_layout.json").write_text(
        json.dumps(adaptive, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8",
    )
    from animation_engine.classroom_math_memory import GLOBAL_SCOPE
    def fact(fid, stage, event, obj, status="established"):
        return {
            "fact_id": fid, "stage_id": stage, "event_id": event,
            "object_id": obj, "status": status, "scope": dict(GLOBAL_SCOPE),
        }
    def recall(rid, fid, stage, event, obj, mode="restate"):
        return {
            "recall_id": rid, "fact_id": fid, "stage_id": stage,
            "event_id": event, "to_object_id": obj, "mode": mode,
            "active_scope": dict(GLOBAL_SCOPE),
        }
    memory = {
        "schema_version": "1.0",
        "mode": "verified_classroom_memory",
        "teacher_reviewed": True,
        "source_flow_sha256": verified.source_sha256,
        "facts": [
            fact("given_legs", "introduce_triangle", "e_intro",
                 "m_legs", status="given"),
            fact("pythagorean_square", "introduce_triangle", "e_apply",
                 "m_square"),
            fact("computed_hypotenuse", "calculate_hypotenuse",
                 "e_hypotenuse", "m_hypotenuse"),
        ],
        "recalls": [
            recall("carry_square", "pythagorean_square",
                   "calculate_hypotenuse", "e_carry", "m_square_handoff"),
            recall("carry_hypotenuse", "computed_hypotenuse",
                   "calculate_perimeter", "e_recap", "m_hypotenuse_recall"),
            recall("restore_original_legs", "given_legs",
                   "calculate_perimeter", "e_legs", "m_legs_recall"),
            recall("use_hypotenuse_in_perimeter", "computed_hypotenuse",
                   "calculate_perimeter", "e_perimeter",
                   "m_perimeter_rule", mode="dependency"),
        ],
        "case_merges": [],
    }
    (root/"math_memory.json").write_text(
        json.dumps(memory, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8",
    )
    return memory


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args()
    data=export_memory_triangle(args.output)
    print("V2_6_3_AUTHORED_TRIANGLE",len(data["facts"]),"facts",
          len(data["recalls"]),"recalls")


if __name__ == "__main__":
    main()
