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
    unit("intro", "完整读题", "题目要求计算给定区间上的定积分。",
         r"I=\int_0^2 2x e^{x^2}\,dx", "题目中的积分表达式。", "observe"),
    unit("strategy", "观察函数结构", "观察指数中的函数和外部系数之间的导数关系。",
         r"\frac{d}{dx}(x^2)=2x", "发现复合函数的内层导数。", "strategy"),
    unit("knowledge", "定积分换元法", "明确新变量与微分的对应关系以及积分限的变换。",
         r"u=g(x),\quad du=g'(x)\,dx", "定积分换元法的一般微分关系。", "knowledge"),
    unit("substitution", "结合本题换元", "将指数中的平方函数设为新变量，替换对应微分。",
         r"u=x^2,\quad du=2x\,dx", "将本题内层函数映射到换元公式。"),
    unit("pitfall", "积分限同步变换", "积分变量改变以后，新变量端点也必须重新计算。",
         r"x=0\Longrightarrow u=0,\quad x=2\Longrightarrow u=4",
         "积分上限从二变成四，不能沿用旧端点。", "pitfall"),
    unit("rewrite", "化为基本积分", "换元之后得到更容易计算的指数函数积分。",
         r"I=\int_0^4 e^u\,du", "同时完成函数、微分和积分限转换。"),
    unit("primitive", "求指数函数原函数", "利用指数函数的原函数进行定积分计算。",
         r"I=\left[e^u\right]_0^4", "由原函数定理得到待代入的表达式。"),
    unit("evaluate", "代入积分上下限", "先取上限对应的函数值，再减去下限对应的值。",
         r"I=e^4-e^0", "将新的积分上下限代入原函数。"),
    unit("conclusion", "积分结果", "利用零次幂等于一得到最终结果。",
         r"I=e^4-1", "给出全题最终结果。", "conclusion"),
    unit("summary", "换元要点回顾", "回顾发现内层导数的方法以及积分限同步变换。",
         None, "结果之后只作简短口播回顾，不重复书写公式。", "summary"),
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

# These lines are teacher-authored natural classroom speech, not labels
# generated from the engine's scene names. They are reviewed BEFORE any TTS.
NARRATION = {
    ("e_intro", "note"):
        "同学们大家好，我们先来看一下这道定积分题。",
    ("e_intro", "math"):
        "计算定积分：",
    ("e_strategy", "note"):
        "这道题我们先观察一下被积函数的结构。指数里面是 x 平方，前面还有一个二 x。这两部分有什么联系？",
    ("e_strategy", "math"):
        "我们先求一下 x 平方的导数：",
    ("e_knowledge", "note"):
        "这里回顾一下定积分换元法。换元时，用新的变量代替内层函数。除了被积函数和微分，积分上下限也要变成新变量对应的值。这一点很重要。",
    ("e_knowledge", "math"):
        "一般的换元关系可以写成：",
    ("e_substitution", "math"):
        "回到这道题。既然指数里面是 x 平方，我们就令：",
    ("e_pitfall", "note"):
        "不过，这是定积分，我们还需要换积分上下限。最容易错的地方，就是只换了函数，却把原来的上下限直接保留下来。因为积分变量已经改变，端点也必须重新计算。",
    ("e_pitfall", "math"):
        "在这道题里，新变量对应的两个端点是：",
    ("e_rewrite", "math"):
        "现在把换元关系和新的积分限代入，原积分就变成：",
    ("e_primitive", "math"):
        "这个积分就很简单了。e 的 u 次幂的原函数还是它本身。所以：",
    ("e_evaluate", "math"):
        "先代入上限四，再减去下限零对应的函数值：",
    ("e_conclusion", "note"):
        "因为 e 的零次方等于一，所以继续化简。",
    ("e_conclusion", "math"):
        "最终得到：",
    ("e_summary", "note"):
        "最后我们简单回顾一下。这道题的关键，是发现指数里的平方函数和前面的二 x，正好构成函数及其导数的关系。遇到这种结构，可以优先考虑换元法，把复合函数积分变成基本积分。另外，定积分换元时，上下限一定要跟着改变。这也是本题最容易出错的地方。好，这道题我们就讲到这里。",
}

# Speaking about the mathematics follows the actual MathTex writing action.
# The first extra paragraph comes AFTER the derivative was written and read,
# so the teacher introduces substitution only after discovering why it fits.
AFTER_MATH = {
    "e_strategy":
        "再来看前面的二 x，恰好就是它的导数。也就是说，指数里的函数和它的导数同时出现。遇到这样的结构，我们就可以把 x 平方看作整体，换成一个新的变量。这样能化成更简单的指数函数积分。这种方法，就是换元法。",
    "e_substitution":
        "这样，原来积分中的二 x d x，就可以用 d u 代替了。",
    "e_pitfall":
        "注意，这里的上限从二变成了四。不能继续使用原来的上限。",
}

READINGS = {
    "m_intro": "I 等于从零到二，二 x 乘以 e 的 x 平方次幂，对 x 的定积分。",
    "m_strategy": "x 平方对 x 求导，等于二 x。",
    "m_knowledge": "令 u 等于 g x，那么 d u 等于 g 撇 x 乘 d x。",
    "m_substitution": "u 等于 x 的平方，d u 等于二 x d x。",
    "m_pitfall": "x 等于零时 u 等于零，x 等于二时 u 等于四。",
    "m_rewrite": "I 等于从零到四，e 的 u 次幂对 u 积分。",
    "m_primitive": "I 等于 e 的 u 次幂，在零到四两端的差。",
    "m_evaluate": "I 等于 e 的四次方减去 e 的零次方。",
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
                if event_id in AFTER_MATH:
                    parts.append({"kind": "text", "value": AFTER_MATH[event_id]})
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
                {"source_text": "计算定积分：", "spoken_text": "计算定积分："},
                {"source_text": r"\quad I=\int_0^2 2x e^{x^2}\,dx",
                 "spoken_text": READINGS["m_intro"]},
            ],
        },
        "strategy": {
            "event_id": "e_strategy", "why_method": "遇到这样的结构，我们就可以把 x 平方看作整体，换成一个新的变量。",
        },
        "knowledge": [{
            "event_id": "e_knowledge", "kind": "formula", "title": "定积分换元法",
            "math_latex": r"u=g(x),\quad du=g'(x)\,dx",
            "spoken_explanation": "这里回顾一下定积分换元法。换元时，用新的变量代替内层函数。",
            "applied_event_id": "e_substitution",
        }],
        "pitfalls": [{
            "event_id": "e_pitfall", "typical_mistake": "换元后仍写旧积分限二",
            "correction": "将新上限算为四并同步更换",
            "spoken_mistake": "最容易错的地方，就是只换了函数，却把原来的上下限直接保留下来。",
            "spoken_correction": "因为积分变量已经改变，端点也必须重新计算。",
        }],
        "conclusion": {
            "event_id": "e_conclusion",
            "spoken_result": "I 等于 e 的四次方减一。",
        },
        "recap": {
            "event_id": "e_summary",
            "spoken_recap": "最后我们简单回顾一下。这道题的关键",
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
