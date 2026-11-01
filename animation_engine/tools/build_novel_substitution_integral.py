"""Novel teacher-reviewed single-engine integral lesson for end-to-end spoken CI.

Question: I = integral_0^1 2x exp(x^2) dx = e - 1.
This exercise is distinct from the archived area/triangle fixtures.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy
from animation_engine.unified_classroom_flow import canonical_sha, checked_flow
from animation_engine.spoken_classroom import checked_spoken, _expected_actions
from build_unified_area_lesson import _export_stage


def unit(ident, heading, detail, tex, reason, phase="calculate"):
    return {
        "id": ident,
        "event_type": "derivation",
        "phase": phase,
        "heading": heading,
        "detail": detail,
        "goal": "按换元法的完整数学依据逐步计算定积分",
        "pause_seconds": 1.5,
        "write_seconds": .85,
        "math": [{"id": ident, "latex": tex, "reason": reason}],
    }


UNITS = [
    unit("intro", "读题并分析被积函数", "观察指数内层与前面的系数，确定换元方向。",
         r"I=\int_0^1 2x e^{x^2}\,dx", "保持原题的积分区间和被积函数。", "strategy"),
    unit("substitution", "选择新的积分变量", "令指数中的平方为新的变量，同时变换微分。",
         r"u=x^2,\quad du=2x\,dx", "复合函数求导与微分关系。"),
    unit("bounds", "同步更换积分上下限", "定积分换元时上下限也要随变量改变。",
         r"x=0\Rightarrow u=0,\quad x=1\Rightarrow u=1", "换元端点对应关系。"),
    unit("rewrite", "写出换元后的积分", "被积函数与微分已变换完整，得到基本指数积分。",
         r"I=\int_0^1 e^u\,du", "换元后的积分完全等价。"),
    unit("primitive", "使用指数函数原函数", "指数函数的原函数仍是自身，保留上下限。",
         r"I=\left[e^u\right]_0^1", "指数函数积分公式。"),
    unit("final", "代入上下限得到结果", "上限代入后减去下限值，得到最终结论。",
         r"I=e-1", "直接计算上下限差。", "summary"),
]

NARRATION = {
    ("e_intro", "note"): "题目要求计算零到一的定积分。被积函数是二乘 x，再乘 e 的 x 平方次幂。",
    ("e_intro", "math"): "我们先把这个积分写下来：",
    ("e_substitution", "math"): "注意到二乘 x，恰好是 x 平方的导数。因此令：",
    ("e_bounds", "math"): "这是定积分。变量变了以后，上下限也必须一起调整：",
    ("e_rewrite", "math"): "现在整个积分就化为：",
    ("e_primitive", "math"): "接下来利用指数函数的积分公式：",
    ("e_final", "note"): "最后代入新变量的上下限，再做一次减法。",
    ("e_final", "math"): "因此，结果为：",
}
READINGS = {
    "m_intro": "I 等于从零到一，二 x 乘 e 的 x 平方次幂，对 x 积分。",
    "m_substitution": "令 u 等于 x 的平方，那么 d u 等于二 x d x。",
    "m_bounds": "x 等于零时 u 等于零，x 等于一时 u 等于一。",
    "m_rewrite": "I 等于从零到一，e 的 u 次幂，对 u 积分。",
    "m_primitive": "I 等于 e 的 u 次幂，在零到一之间的取值之差。",
    "m_final": "I 等于 e 减一。",
}


def build(root: Path):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    problem = r"计算定积分：\quad I=\int_0^1 2x e^{x^2}\,dx"
    reference = "\n".join([problem] + [m["latex"] for u in UNITS for m in u["math"]])
    package, board, execution, cues = compile_teaching_units(
        problem=problem, reference_solution=reference,
        units=UNITS, teacher_reviewed=True,
    )
    _export_stage(
        root / "integration", package=package, board=board,
        execution=execution, cues=cues, policy=simple_classroom_policy(),
        units=UNITS,
    )
    source = {
        "schema_version": "1.0", "mode": "unified_classroom_flow",
        "teacher_reviewed": True, "lesson_id": "novel_exponential_substitution",
        "problem": problem,
        "reference_solution_sha256": canonical_sha(reference),
        "stages": [{
            "stage_id": "integration", "engine": "standard",
            "directory": "integration",
            "package_sha256": package["validated_content_sha256"],
            "source_storyboard_sha256": execution.source_storyboard_sha256,
            "event_ids": [e.event_id for e in board.scenes], "handoff": [],
        }],
    }
    (root / "unified_flow.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    flow = checked_flow(root / "unified_flow.json")
    events = []
    for plan in _expected_actions(flow, adaptive=False):
        spans = []
        for kind, obj, tex in plan["actions"]:
            event_id = plan["event_id"]
            preamble = NARRATION[(event_id, kind)]
            parts = [{"kind": "text", "value": preamble}]
            if kind == "math":
                parts.append({"kind": "math", "latex": tex, "reading": READINGS[obj]})
            spans.append({"kind": kind, "object_id": obj, "parts": parts})
        events.append({
            "stage_id": "integration",
            "event_id": plan["event_id"],
            "pedagogical_cue_covered": True,
            "spans": spans,
            "question_read_aloud": len(events) == 0,
            "question_source_sha256": canonical_sha(problem) if not events else None,
        })
    spoken = {
        "schema_version": "1.0", "mode": "verified_spoken_classroom",
        "teacher_reviewed": True, "source_flow_sha256": flow.source_sha256,
        "voice": "zh-CN-XiaoxiaoNeural", "speech_rate": "+1%",
        "events": events,
    }
    (root / "spoken_classroom.json").write_text(
        json.dumps(spoken, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    assert checked_spoken(root / "spoken_classroom.json", adaptive=False)
    return spoken


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    created = build(args.output)
    print("NEW_INTEGRAL_SINGLE_ENGINE", len(created["events"]))
