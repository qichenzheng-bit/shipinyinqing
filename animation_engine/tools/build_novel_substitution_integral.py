"""V2.7 reviewed substitution lesson: script-first teacher narration and recap.

Question: integral from 0 to 2 of 2x exp(x^2) dx = exp(4) - 1.
A changed upper bound is deliberate: copying the original bounds is wrong.
No AI mathematical claims are certified by this author-reviewed fixture.
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
        "goal": "按定积分换元的数学依据完整计算，并讲清典型错误",
        "pause_seconds": 1.5,
        "write_seconds": .85,
        "math": ([{"id": ident, "latex": tex, "reason": reason}]
                 if tex is not None else []),
    }


UNITS = [
    unit("intro", "完整读题", "已知被积函数和积分上下限，目标是求定积分。",
         r"I=\int_0^2 2x e^{x^2}\,dx", "原题数学表达式必须原样保留。", "observe"),
    unit("strategy", "观察复合结构", "指数内是平方函数，外部恰好有对应的导数因子。",
         r"\frac{d}{dx}(x^2)=2x", "说明为什么优先考虑换元。", "strategy"),
    unit("knowledge", "定积分换元法", "以新变量代替内层函数，微分及上下限须同步变换。",
         r"u=g(x),\quad du=g'(x)\,dx", "换元法的一般微分关系及适用结构。", "knowledge"),
    unit("substitution", "选择新变量", "令新变量等于平方函数，利用微分关系变换被积函数。",
         r"u=x^2,\quad du=2x\,dx", "将本题映射到通用换元公式。"),
    unit("pitfall", "积分限同步变换", "不能只换被积函数而保留原端点，必须重算新端点。",
         r"x=0\Longrightarrow u=0,\quad x=2\Longrightarrow u=4",
         "本题上限从二变为四，展示实际易错风险。", "pitfall"),
    unit("rewrite", "化为基础指数积分", "完成变量和积分限转换后，得到标准指数积分。",
         r"I=\int_0^4 e^u\,du", "全部变量和界限同时换元。"),
    unit("primitive", "利用指数积分公式", "原函数是同一个指数函数，按新端点计算。",
         r"I=\left[e^u\right]_0^4", "指数函数原函数。"),
    unit("conclusion", "积分结果", "依次代入四和零，取上限值减下限值。",
         r"I=e^4-1", "全题的实际最终结论。", "conclusion"),
    unit("summary", "换元要点回顾", "记住复合结构和对应导数，尤其避免漏换定积分限。",
         None, "本题结果后以简短讲稿回顾方法与易错点。", "summary"),
]

KNOWLEDGE_CATALOG = {
    "schema_version": "1.0", "teacher_reviewed": True,
    "points": [{
        "event_id": "e_knowledge",
        "topic_id": "definite_integral_substitution",
        "title": "定积分换元法", "kind": "formula",
        "formulae": [{
            "object_id": "m_knowledge",
            "latex": r"u=g(x),\quad du=g'(x)\,dx",
        }],
        "used_in": ["e_substitution"],
    }],
}

NARRATION = {
    ("e_intro", "note"):
        "同学们大家好，我们先来看一下这道定积分题。题目要求计算从零到二的定积分。被积函数是二乘 x，乘 e 的 x 平方次幂。",
    ("e_intro", "math"): "我们把题目中的积分完整读出来：",
    ("e_strategy", "note"):
        "先观察被积函数的结构。指数里面是 x 平方，前面恰好有二乘 x。为什么考虑换元法呢？因为它是内层的导数。",
    ("e_strategy", "math"): "先把这个关键导数关系写清楚：",
    ("e_knowledge", "note"):
        "这里用的是定积分换元法。它的核心是用新变量表示内层函数，同时把微分换成新变量。",
    ("e_knowledge", "math"): "相应的一般关系可以写成：",
    ("e_substitution", "math"):
        "结合本题，令 u 等于 x 的平方。于是微分关系是：",
    ("e_pitfall", "note"):
        "最容易错的是只换函数，忘了换上下限。正确做法是把原端点代入换元关系，重新计算积分限。这里上限从二变成四。",
    ("e_pitfall", "math"): "因此，新变量对应的积分上下限是：",
    ("e_rewrite", "math"): "把变量、微分和上下限都换好，原积分就变成：",
    ("e_primitive", "math"): "指数函数的原函数还是指数函数。按新变量积分，得到：",
    ("e_conclusion", "note"): "最后，用上限四对应的函数值减去下限零对应的函数值。",
    ("e_conclusion", "math"): "因此本题的最终结果是：",
    ("e_summary", "note"):
        "最后归纳一下。这题的关键是认出复合函数和它的内层导数。要熟悉换元法。尤其注意，换元后积分上下限必须同步改。",
}

READINGS = {
    "m_intro": "I 等于从零到二，二 x 乘 e 的 x 平方次幂，对 x 积分。",
    "m_strategy": "x 的平方对 x 求导，等于二 x。",
    "m_knowledge": "令 u 等于 g x，那么 d u 等于 g 撇 x 乘 d x。",
    "m_substitution": "u 等于 x 的平方，d u 等于二 x d x。",
    "m_pitfall": "x 等于零时 u 等于零，x 等于二时 u 等于四。",
    "m_rewrite": "I 等于从零到四，e 的 u 次幂对 u 积分。",
    "m_primitive": "I 等于 e 的 u 次幂，在零到四两端的差。",
    "m_conclusion": "I 等于 e 的四次方减一。",
}


def build(root: Path):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    problem = r"计算定积分：\quad I=\int_0^2 2x e^{x^2}\,dx"
    reference = "\n".join([problem] + [m["latex"] for u in UNITS for m in u["math"]])
    package, board, execution, cues = compile_teaching_units(
        problem=problem, reference_solution=reference, units=UNITS,
        teacher_reviewed=True, knowledge_catalog=KNOWLEDGE_CATALOG,
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
    for action in _expected_actions(flow, adaptive=False):
        spans = []
        for kind, obj, tex in action["actions"]:
            event_id = action["event_id"]
            text = NARRATION[(event_id, kind)]
            parts = [{"kind": "text", "value": text}]
            if kind == "math":
                parts.append({"kind": "math", "latex": tex, "reading": READINGS[obj]})
            spans.append({"kind": kind, "object_id": obj, "parts": parts})
        events.append({
            "stage_id": "integration", "event_id": action["event_id"],
            "pedagogical_cue_covered": True, "spans": spans,
            "question_read_aloud": len(events) == 0,
            "question_source_sha256": canonical_sha(problem) if not events else None,
        })

    lesson_contract = {
        "version": "2.7", "problem_type": "定积分",
        "opening": {
            "event_id": "e_intro",
            "opening_text": "同学们大家好，我们先来看一下这道定积分题。",
            "question_segments": [
                {"source_text": "计算定积分：", "spoken_text": "题目要求计算从零到二的定积分。"},
                {"source_text": r"\quad I=\int_0^2 2x e^{x^2}\,dx",
                 "spoken_text": READINGS["m_intro"]},
            ],
        },
        "strategy": {
            "event_id": "e_strategy", "why_method": "为什么考虑换元法呢？因为它是内层的导数。",
        },
        "knowledge": [{
            "event_id": "e_knowledge", "kind": "formula", "title": "定积分换元法",
            "math_latex": r"u=g(x),\quad du=g'(x)\,dx",
            "spoken_explanation": "这里用的是定积分换元法。它的核心是用新变量表示内层函数",
            "applied_event_id": "e_substitution",
        }],
        "pitfalls": [{
            "event_id": "e_pitfall", "typical_mistake": "换元后仍写旧积分限二",
            "correction": "将新上限算为四并同步更换",
            "spoken_mistake": "最容易错的是只换函数，忘了换上下限。",
            "spoken_correction": "正确做法是把原端点代入换元关系，重新计算积分限。",
        }],
        "conclusion": {
            "event_id": "e_conclusion",
            "spoken_result": "I 等于 e 的四次方减一。",
        },
        "recap": {
            "event_id": "e_summary",
            "spoken_recap": "最后归纳一下。这题的关键是认出复合函数和它的内层导数。",
        },
    }
    spoken = {
        "schema_version": "1.0", "mode": "verified_spoken_classroom",
        "teacher_reviewed": True, "source_flow_sha256": flow.source_sha256,
        "voice": "zh-CN-XiaoxiaoNeural", "speech_rate": "+1%",
        "lesson_contract": lesson_contract, "events": events,
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
    print("V27_NEW_INTEGRAL_REVIEWED", len(created["events"]))
