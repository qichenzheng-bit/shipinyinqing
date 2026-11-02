"""Independent final-acceptance fixture: a NEW trigonometric limit lesson.

The mathematics, storyboard, spoken readings and recap below are authored
deterministically.  No LLM, provider credential, or live model is invoked.
This is a QA fixture, not an automatically teacher-approved user lesson.
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


def unit(name, heading, detail, tex, reason, phase="calculate"):
    return {
        "id": name, "event_type": "derivation", "phase": phase,
        "heading": heading, "detail": detail,
        "goal": "用正弦余弦泰勒展开，逐步处理三次项与括号符号",
        "pause_seconds": 1.1, "write_seconds": .85,
        "math": ([{"id": name, "latex": tex, "reason": reason}]
                 if tex is not None else []),
    }


UNITS = [
    unit("intro", "完整读题", "求一个含正弦与余弦的三阶极限。",
         r"L=\lim_{x\to0}\frac{\sin x-x\cos x}{x^3}",
         "题干原文，不能省略分子整体。", "observe"),
    unit("strategy", "观察一次项", "正弦与变量乘余弦的乘积具有相同的一次项。",
         r"\sin x\sim x,\quad x\cos x\sim x",
         "一次项抵消，需继续求三次项。", "strategy"),
    unit("sine", "正弦三阶泰勒展开", "展开正弦到三阶，并保留高阶余项。",
         r"\sin x=x-\frac{x^3}{6}+o(x^3)",
         "使用原点处正弦的三阶泰勒展开。", "knowledge"),
    unit("cosine", "余弦二阶泰勒展开", "乘变量之前只需余弦的二阶展开。",
         r"\cos x=1-\frac{x^2}{2}+o(x^2)",
         "乘以 x 后得到三次级数。", "knowledge"),
    unit("product", "余弦乘以变量", "余弦展开整体乘以变量，余项阶数也增加。",
         r"x\cos x=x-\frac{x^3}{2}+o(x^3)",
         "x o(x^2)=o(x^3)。"),
    unit("substitute", "代入原分子", "保留第二个括号外的负号，避免直接跳步。",
         r"\sin x-x\cos x=(x-\frac{x^3}{6}+o(x^3))-(x-\frac{x^3}{2}+o(x^3))",
         "分别代入两条有来源的展开式。"),
    unit("pitfall", "括号前的负号", "减去整个余弦乘积时，括号内部每项都变号。",
         r"-(x-\frac{x^3}{2})=-x+\frac{x^3}{2}",
         "第二个三次项最终为正，不能写成负。", "pitfall"),
    unit("cancel", "抵消一次项", "一次项抵消；高阶余项合并后仍为高阶余项。",
         r"\sin x-x\cos x=-\frac{x^3}{6}+\frac{x^3}{2}+o(x^3)",
         "一阶项抵消，三次项保留各自符号。"),
    unit("combine", "合并三次项", "负六分之一与正二分之一相加。",
         r"\sin x-x\cos x=\frac{x^3}{3}+o(x^3)",
         "三次项系数为三分之一。"),
    unit("divide", "回到极限式", "分子整体除以变量的三次方。",
         r"L=\lim_{x\to0}\left(\frac13+\frac{o(x^3)}{x^3}\right)",
         "按小 o 定义，第二项趋于零。"),
    unit("conclusion", "极限结果", "得到原题的极限值。",
         r"L=\frac13", "给出最终结果。", "conclusion"),
    unit("summary", "核心知识与易错点", "回顾泰勒阶数与负号。",
         None, "不再重复书写答案，只简短回顾知识点。", "summary"),
]

KNOWLEDGE_CATALOG = {
    "schema_version": "1.0", "teacher_reviewed": True,
    "points": [
        {
            "event_id": "e_sine", "topic_id": "sine_third_order_taylor",
            "title": "正弦三阶泰勒展开", "kind": "formula",
            "formulae": [{"object_id": "m_sine",
                          "latex": r"\sin x=x-\frac{x^3}{6}+o(x^3)"}],
            "used_in": ["e_substitute"],
        },
        {
            "event_id": "e_cosine", "topic_id": "cosine_second_order_taylor",
            "title": "余弦二阶泰勒展开", "kind": "formula",
            "formulae": [{"object_id": "m_cosine",
                          "latex": r"\cos x=1-\frac{x^2}{2}+o(x^2)"}],
            "used_in": ["e_product"],
        },
    ],
}

NARRATION = {
    ("e_intro", "note"): "同学们大家好，我们先来看一下这道极限题。",
    ("e_intro", "math"): "求极限：",
    ("e_strategy", "note"):
        "观察分子，正弦 x 减去 x 乘余弦 x。它们的一次项相同，而分母是 x 的三次方。我们需要找出抵消后留下的三次项。",
    ("e_strategy", "math"): "先看最简单的一次近似：",
    ("e_sine", "note"):
        "先写正弦函数在零点处的三阶泰勒展开，注意负六分之一这个系数。",
    ("e_sine", "math"): "正弦的展开式是：",
    ("e_cosine", "note"):
        "再看余弦。因为原式中还有一个 x，余弦只要展开到二次项就够了。",
    ("e_cosine", "math"): "余弦的展开式是：",
    ("e_product", "note"):
        "现在把余弦的展开式整体乘以 x。注意小 o 余项也要乘 x。",
    ("e_product", "math"): "于是：",
    ("e_substitute", "note"):
        "把刚才两条展开式代回分子。这里先保留括号，避免把减号看漏。",
    ("e_substitute", "math"): "原分子变为：",
    ("e_pitfall", "note"):
        "这里是最容易算错的地方。第二个括号前面是负号，所以括号里的每一项都需要变号。",
    ("e_pitfall", "math"): "特别是三次项：",
    ("e_cancel", "note"):
        "现在去括号。x 和负 x 相消，两个三次项留下来。两处高阶余项合在一起，仍然是小 o 的 x 三次方。",
    ("e_cancel", "math"): "所以分子等于：",
    ("e_combine", "note"):
        "负六分之一加二分之一，通分后就是三分之一。",
    ("e_combine", "math"): "整理成：",
    ("e_divide", "note"):
        "把这个表达式代回原来的极限，再整体除以 x 的三次方。",
    ("e_divide", "math"): "得到：",
    ("e_conclusion", "note"):
        "根据小 o 的定义，最后的余项比值趋于零。",
    ("e_conclusion", "math"): "因此结果是：",
    ("e_summary", "note"):
        "最后归纳一下。这道题的关键，是掌握正弦的三阶展开、余弦的二阶展开。要找准分子中第一次不抵消的项。还要注意减去整个括号时，负号必须作用到每一项。",
}

AFTER_MATH = {
    "e_strategy": "所以只用等价无穷小还不能求出结果，下一步要展开到三次项。",
    "e_cosine": "外面乘一次 x，正好把二次项变成三次项。",
    "e_pitfall": "这里是加二分之一 x 三次方，不是减二分之一。",
    "e_divide": "小 o 的 x 三次方除以 x 三次方，极限是零。",
}

READINGS = {
    "m_intro":
        "L 等于 x 趋于零时，正弦 x 减去 x 乘余弦 x，整体除以 x 三次方的极限。",
    "m_strategy": "正弦 x 与 x 等价，x 乘余弦 x 也与 x 等价。",
    "m_sine": "正弦 x 等于 x 减六分之一 x 三次方，加小 o 的 x 三次方。",
    "m_cosine": "余弦 x 等于一减二分之一 x 平方，加小 o 的 x 平方。",
    "m_product": "x 乘余弦 x 等于 x 减二分之一 x 三次方，加小 o 的 x 三次方。",
    "m_substitute":
        "正弦 x 减 x 乘余弦 x，等于第一组括号 x 减六分之一 x 三次方加小 o 的 x 三次方，减去第二组括号 x 减二分之一 x 三次方加小 o 的 x 三次方。",
    "m_pitfall": "负的括号 x 减二分之一 x 三次方，等于负 x 加二分之一 x 三次方。",
    "m_cancel":
        "正弦 x 减 x 乘余弦 x，等于负六分之一 x 三次方，加二分之一 x 三次方，加小 o 的 x 三次方。",
    "m_combine":
        "正弦 x 减 x 乘余弦 x，等于三分之一 x 三次方，加小 o 的 x 三次方。",
    "m_divide":
        "L 等于 x 趋于零时，三分之一加上小 o 的 x 三次方除以 x 三次方的极限。",
    "m_conclusion": "L 等于三分之一。",
}


def build(root: Path):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    problem = r"求极限：\quad L=\lim_{x\to0}\frac{\sin x-x\cos x}{x^3}"
    reference = "\n".join([problem] + [
        item["latex"] for entry in UNITS for item in entry["math"]
    ])
    package, board, execution, cues = compile_teaching_units(
        problem=problem, reference_solution=reference,
        units=UNITS, teacher_reviewed=True,
        knowledge_catalog=KNOWLEDGE_CATALOG,
    )
    _export_stage(
        root / "trig_limit", package=package, board=board,
        execution=execution, cues=cues,
        policy=simple_classroom_policy(), units=UNITS,
        knowledge=KNOWLEDGE_CATALOG,
    )
    source = {
        "schema_version": "1.0", "mode": "unified_classroom_flow",
        "teacher_reviewed": True, "lesson_id": "final_fresh_sine_cosine_limit",
        "problem": problem, "reference_solution_sha256": canonical_sha(reference),
        "stages": [{
            "stage_id": "trig_limit", "engine": "standard",
            "directory": "trig_limit",
            "package_sha256": package["validated_content_sha256"],
            "source_storyboard_sha256": execution.source_storyboard_sha256,
            "event_ids": [event.event_id for event in board.scenes],
            "handoff": [],
        }],
    }
    (root / "unified_flow.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    flow = checked_flow(root / "unified_flow.json")
    events = []
    for action in _expected_actions(flow, adaptive=False):
        spans = []
        for kind, obj, tex in action["actions"]:
            event_id = action["event_id"]
            parts = [{"kind": "text", "value": NARRATION[(event_id, kind)]}]
            if kind == "math":
                parts.append({
                    "kind": "math", "latex": tex, "reading": READINGS[obj],
                })
                if event_id in AFTER_MATH:
                    parts.append({
                        "kind": "text", "value": AFTER_MATH[event_id],
                    })
            spans.append({
                "kind": kind, "object_id": obj, "parts": parts,
            })
        events.append({
            "stage_id": "trig_limit", "event_id": action["event_id"],
            "pedagogical_cue_covered": True, "spans": spans,
            "question_read_aloud": len(events) == 0,
            "question_source_sha256": (
                canonical_sha(problem) if not events else None
            ),
        })

    lesson_contract = {
        "version": "2.7", "problem_type": "极限",
        "opening": {
            "event_id": "e_intro",
            "opening_text": NARRATION[("e_intro", "note")],
            "question_segments": [
                {"source_text": "求极限：", "spoken_text": "求极限："},
                {
                    "source_text": r"\quad L=\lim_{x\to0}\frac{\sin x-x\cos x}{x^3}",
                    "spoken_text": READINGS["m_intro"],
                },
            ],
        },
        "strategy": {
            "event_id": "e_strategy",
            "why_method": "下一步要展开到三次项。",
        },
        "knowledge": [
            {
                "event_id": "e_sine", "kind": "formula",
                "title": "正弦三阶泰勒展开",
                "math_latex": r"\sin x=x-\frac{x^3}{6}+o(x^3)",
                "spoken_explanation": "先写正弦函数在零点处的三阶泰勒展开",
                "applied_event_id": "e_substitute",
            },
            {
                "event_id": "e_cosine", "kind": "formula",
                "title": "余弦二阶泰勒展开",
                "math_latex": r"\cos x=1-\frac{x^2}{2}+o(x^2)",
                "spoken_explanation": "余弦只要展开到二次项就够了",
                "applied_event_id": "e_product",
            },
        ],
        "pitfalls": [{
            "event_id": "e_pitfall",
            "typical_mistake": "减去 x cos x 时遗漏括号前负号",
            "correction": "将负号分配到括号中每一项",
            "spoken_mistake": "第二个括号前面是负号",
            "spoken_correction": "括号里的每一项都需要变号。",
        }],
        "conclusion": {
            "event_id": "e_conclusion",
            "spoken_result": READINGS["m_conclusion"],
        },
        "recap": {
            "event_id": "e_summary",
            "spoken_recap": "最后归纳一下。这道题的关键，是掌握正弦的三阶展开",
        },
    }
    spoken = {
        "schema_version": "1.0", "mode": "verified_spoken_classroom",
        "teacher_reviewed": True, "source_flow_sha256": flow.source_sha256,
        "voice": "zh-CN-XiaoxiaoNeural", "speech_rate": "+5%",
        "lesson_contract": lesson_contract, "events": events,
    }
    (root / "spoken_classroom.json").write_text(
        json.dumps(spoken, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    assert checked_spoken(root / "spoken_classroom.json", adaptive=False)
    return spoken


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print("FINAL_FRESH_TRIG_LIMIT_REVIEWED_EVENTS", len(build(args.output)["events"]))
