"""Produce original source-verified V2.6.2 keep/hide/restore classroom cases.

Uses approved V2.6.1 mathematics unchanged. Optional third stage revisits the
already computed exact result while restoring the *previous* graph memento.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy
from animation_engine.unified_classroom_flow import canonical_sha, checked_flow
from build_unified_area_lesson import export_lesson, _export_stage
from build_diagram_classroom_lesson import formula, unit


def export_adaptive_lesson(destination: Path, mode: str = "hold") -> dict:
    if mode not in ("hold", "hide", "restore"):
        raise ValueError("ADAPTIVE_DEMO_UNSUPPORTED_MODE")
    root = Path(destination)
    original = export_lesson(root)
    source = json.loads((root/"graph"/"teaching_package.json").read_text(
        encoding="utf-8"))["source"]
    if mode == "restore":
        # The first write must be the EXACT proved result handed over from
        # the preceding calculation stage. No new mathematical claim.
        units = [unit(
            "review", "回到图像核对面积结果",
            "结合此前的函数图像，核对得到的非负面积。",
            [formula("area_review", r"S=\frac12-\frac13=\frac16",
                     "已计算出的面积与图像中的有界区域一致。")],
            phase="summary",
        )]
        package, board, execution, cues = compile_teaching_units(
            problem=source["problem"],
            reference_solution=source["reference_solution"],
            units=units, teacher_reviewed=True,
        )
        _export_stage(
            root/"review", package=package, board=board, execution=execution,
            cues=cues, policy=simple_classroom_policy(), units=units,
        )
        original["stages"].append({
            "stage_id": "review_graph",
            "engine": "standard",
            "directory": "review",
            "package_sha256": package["validated_content_sha256"],
            "source_storyboard_sha256": execution.source_storyboard_sha256,
            "event_ids": [x.event_id for x in board.scenes],
            "handoff": [{
                "from_stage": "integral_calculation",
                "from_object_id": "m_area_evaluated",
                "to_object_id": "m_area_review",
            }],
        })
        (root/"unified_flow.json").write_text(
            json.dumps(original, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    checked = checked_flow(root/"unified_flow.json")
    source_stage = checked.stages[0].stage_id
    specs = [{
        "stage_id": source_stage,
        "layout": "diagram_native",
        "diagram_action": "create",
        "diagram_source_stage": source_stage,
        "teaching_reason": "首次建立真实函数与定积分区域的图形",
    }, {
        "stage_id": "integral_calculation",
        "layout": "full_width" if mode in ("hide", "restore") else
                  "math_left_diagram_right",
        "diagram_action": "hide" if mode in ("hide", "restore") else "hold",
        "diagram_source_stage": source_stage,
        "teaching_reason": (
            "本阶段计算不再依赖图像，释放整幅板书"
            if mode in ("hide", "restore") else
            "本阶段继续参照图像判断积分式，跨幕保持图像"
        ),
    }]
    if mode == "restore":
        specs.append({
            "stage_id": "review_graph",
            "layout": "math_left_diagram_right",
            "diagram_action": "restore",
            "diagram_source_stage": source_stage,
            "teaching_reason": "重新参照原图核对积分结果，恢复完整图像状态",
        })
    data = {
        "schema_version": "1.0",
        "mode": "adaptive_classroom_layout",
        "teacher_reviewed": True,
        "source_flow_sha256": canonical_sha(original),
        "stages": specs,
    }
    (root/"adaptive_layout.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=["hold", "hide", "restore"],
                        default="hold")
    args = parser.parse_args()
    result = export_adaptive_lesson(args.output, args.mode)
    print("V2_6_2_ADAPTIVE_EXPORTED", args.mode, len(result["stages"]))


if __name__ == "__main__":
    main()
