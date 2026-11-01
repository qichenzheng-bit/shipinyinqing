"""One-off, independent V2.7 real classroom acceptance: third-order log limit.

Not an installed lesson, production fixture, or change to the main engine.
The solution and all readings were freshly authored and independently checked.
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
        "goal": "从低阶项抵消识别三阶泰勒展开，并说明小 o 余项的作用",
        "pause_seconds": 1.4, "write_seconds": .82,
        "math": ([{"id": name, "latex": tex, "reason": reason}]
                 if tex is not None else []),
    }


UNITS = [
    unit("intro", "完整读题", "求给定对数函数表达式在原点处的极限。",
         r"L=\lim_{x\to0}\frac{\ln(1+x)-x+\frac{x^2}{2}}{x^3}",
         "忠实读出分子括号与分母的整体结构。", "observe"),
    unit("strategy", "观察低阶项", "分子故意减去一次项又加回二次项，分母是三次方。",
         r"\ln(1+x)=x-\frac{x^2}{2}+\cdots",
         "先观察自然对数的低阶展开结构，再解释方法。", "strategy"),
    unit("knowledge", "三阶泰勒展开", "自然对数展开至三阶，需要保留比三次方更高阶的余项。",
         r"\ln(1+x)=x-\frac{x^2}{2}+\frac{x^3}{3}+o(x^3)",
         "在零点处使用自然对数的三阶泰勒公式。", "knowledge"),
    unit("substitute", "代入原分子", "将展开式代入原极限，暂时保留各项以便检查符号。",
         r"L=\lim_{x\to0}\frac{x-\frac{x^2}{2}+\frac{x^3}{3}+o(x^3)-x+\frac{x^2}{2}}{x^3}",
         "原有的减 x 和加二分之一 x 平方没有被漏掉。"),
    unit("cancel", "合并同类项", "分子中的一次项和二次项恰好抵消。",
         r"L=\lim_{x\to0}\frac{\frac{x^3}{3}+o(x^3)}{x^3}",
         "抵消一次、二次项之后留下三次首项及高阶余项。"),
    unit("divide", "分开两项", "分子两项分别除以分母中的三次方。",
         r"L=\lim_{x\to0}\left(\frac13+\frac{o(x^3)}{x^3}\right)",
         "三次项的系数直接成为常数三分之一。"),
    unit("pitfall", "展开阶数与余项", "只展开到二次无法找出首项，须保留三次项和余项。",
         r"\lim_{x\to0}\frac{o(x^3)}{x^3}=0",
         "小 o 三次方除以 x 三次方趋零，大 O 三次方则不足以保证该结论。",
         "pitfall"),
    unit("conclusion", "极限结果", "利用高阶余项趋零，得到正确的极限。",
         r"L=\frac13", "自然对数展开所得最终结论。", "conclusion"),
    unit("summary", "核心思路回顾", "观察抵消关系，选三阶展开，处理高阶余项。",
         None, "结论之后讲方法与易错点，不再重复展示结果。", "summary"),
]

KNOWLEDGE_CATALOG = {
    "schema_version": "1.0", "teacher_reviewed": True,
    "points": [{
        "event_id": "e_knowledge", "topic_id": "log_one_plus_t_taylor_order_three",
        "title": "三阶泰勒展开", "kind": "formula",
        "formulae": [{
            "object_id": "m_knowledge",
            "latex": r"\ln(1+x)=x-\frac{x^2}{2}+\frac{x^3}{3}+o(x^3)",
        }],
        "used_in": ["e_substitute"],
    }],
}

NARRATION = {
    ("e_intro", "note"):
        "同学们大家好，我们先来看一下这道极限题。",
    ("e_intro", "math"): "求极限：",
    ("e_strategy", "note"):
        "先观察分子的结构。它在对数函数后面减去了 x，又加上二分之一 x 平方。分母则是 x 的三次方。我们想一想，这几个项有什么联系？",
    ("e_strategy", "math"):
        "从自然对数的低阶表达式来看：",
    ("e_knowledge", "note"):
        "这里用到的是自然对数在零点的泰勒展开。因为分母是三次方，所以我们不能只保留前两项。要把三次项也写出来。",
    ("e_knowledge", "math"):
        "它的三阶展开公式是：",
    ("e_substitute", "math"):
        "现在把展开式代入原极限。先不要急着合并，把各项都写出来：",
    ("e_cancel", "math"):
        "你看，分子中的 x 与负 x 相消。负二分之一 x 平方与正二分之一 x 平方，也正好相消。于是得到：",
    ("e_divide", "math"):
        "接着让分子中的两项分别除以 x 的三次方，就得到：",
    ("e_pitfall", "note"):
        "这里有一个常见的易错点。如果只展开到二次项，低阶项消掉以后，就找不到三次项的系数。所以必须展开到三阶。还要注意高阶余项。",
    ("e_pitfall", "math"):
        "因为是小 o 的三次方余项，所以除以 x 的三次方后会趋近零：",
    ("e_conclusion", "note"):
        "这样，后面那一项趋近零，只剩下三分之一。",
    ("e_conclusion", "math"):
        "所以本题的极限结果是：",
    ("e_summary", "note"):
        "最后归纳一下。这道题的关键是掌握自然对数的三阶泰勒展开。注意根据分母的次数选择展开阶数，同时正确处理高阶余项，尤其要区分小 o 和大 O。",
}

AFTER_MATH = {
    "e_strategy":
        "这里的一次项与二次项，恰好会跟原分子后面的两项抵消。要找到真正留下来的三次项，就需要把对数函数继续展开。这就自然想到使用泰勒展开。",
    "e_pitfall":
        "如果把这里随意写成大 O 三次方，就不能直接得到趋近零的结论。",
}

READINGS = {
    "m_intro":
        "L 等于 x 趋近零时，ln 一加 x 减 x 加二分之一 x 平方，整体除以 x 三次方的极限。",
    "m_strategy":
        "ln 一加 x，等于 x 减二分之一 x 平方，后面还有更高阶项。",
    "m_knowledge":
        "ln 一加 x，等于 x 减二分之一 x 平方，加三分之一 x 三次方，再加小 o 的 x 三次方。",
    "m_substitute":
        "L 等于 x 趋近零时，分子是 x 减二分之一 x 平方，加三分之一 x 三次方，加小 o 的 x 三次方，再减 x 加二分之一 x 平方。整体除以 x 三次方的极限。",
    "m_cancel":
        "L 等于 x 趋近零时，三分之一 x 三次方加小 o 的 x 三次方，整体除以 x 三次方的极限。",
    "m_divide":
        "L 等于 x 趋近零时，三分之一加小 o 的 x 三次方除以 x 三次方的极限。",
    "m_pitfall":
        "当 x 趋近零时，小 o 的 x 三次方除以 x 三次方，极限等于零。",
    "m_conclusion":
        "L 等于三分之一。",
}


def build(root: Path):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    problem = r"求极限：\quad L=\lim_{x\to0}\frac{\ln(1+x)-x+\frac{x^2}{2}}{x^3}"
    reference = "\n".join([problem] + [m["latex"] for u in UNITS for m in u["math"]])
    package, board, execution, cues = compile_teaching_units(
        problem=problem, reference_solution=reference, units=UNITS,
        teacher_reviewed=True, knowledge_catalog=KNOWLEDGE_CATALOG,
    )
    _export_stage(
        root / "limit", package=package, board=board,
        execution=execution, cues=cues, policy=simple_classroom_policy(),
        units=UNITS,
    )
    source = {
        "schema_version": "1.0", "mode": "unified_classroom_flow",
        "teacher_reviewed": True, "lesson_id": "independent_logarithmic_third_order_limit",
        "problem": problem,
        "reference_solution_sha256": canonical_sha(reference),
        "stages": [{
            "stage_id": "limit", "engine": "standard", "directory": "limit",
            "package_sha256": package["validated_content_sha256"],
            "source_storyboard_sha256": execution.source_storyboard_sha256,
            "event_ids": [e.event_id for e in board.scenes], "handoff": [],
        }],
    }
    (root/"unified_flow.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2)+"\n", encoding="utf-8"
    )
    flow = checked_flow(root/"unified_flow.json")
    events = []
    for action in _expected_actions(flow, adaptive=False):
        spans = []
        for kind, obj, tex in action["actions"]:
            event_id = action["event_id"]
            text = NARRATION[(event_id, kind)]
            parts = [{"kind":"text", "value":text}]
            if kind=="math":
                parts.append({"kind":"math", "latex":tex, "reading":READINGS[obj]})
                if event_id in AFTER_MATH:
                    parts.append({"kind":"text", "value":AFTER_MATH[event_id]})
            spoken_span={"kind":kind, "object_id":obj, "parts":parts}
            if event_id=="e_cancel" and kind=="math":
                spoken_span["emphasis_cues"]=[
                    {
                        "source_object_id":"m_substitute",
                        "latex_fragment":"-x",
                        "occurrence":0,
                        "spoken_phrase":"分子中的 x 与负 x 相消。",
                        "effect":"highlight",
                    },
                    {
                        "source_object_id":"m_substitute",
                        "latex_fragment":r"+\frac{x^2}{2}",
                        "occurrence":0,
                        "spoken_phrase":"负二分之一 x 平方与正二分之一 x 平方，",
                        "effect":"highlight",
                    },
                ]
            spans.append(spoken_span)
        events.append({
            "stage_id":"limit", "event_id":action["event_id"],
            "pedagogical_cue_covered":True, "spans":spans,
            "question_read_aloud":len(events)==0,
            "question_source_sha256":canonical_sha(problem) if not events else None,
        })
    lesson_contract = {
        "version":"2.7", "problem_type":"极限",
        "opening":{
            "event_id":"e_intro",
            "opening_text":"同学们大家好，我们先来看一下这道极限题。",
            "question_segments":[
                {"source_text":"求极限：","spoken_text":"求极限："},
                {"source_text":r"\quad L=\lim_{x\to0}\frac{\ln(1+x)-x+\frac{x^2}{2}}{x^3}",
                 "spoken_text":READINGS["m_intro"]},
            ],
        },
        "strategy":{
            "event_id":"e_strategy",
            "why_method":"要找到真正留下来的三次项，就需要把对数函数继续展开。",
        },
        "knowledge":[{
            "event_id":"e_knowledge", "kind":"formula",
            "title":"三阶泰勒展开",
            "math_latex":r"\ln(1+x)=x-\frac{x^2}{2}+\frac{x^3}{3}+o(x^3)",
            "spoken_explanation":"这里用到的是自然对数在零点的泰勒展开。",
            "applied_event_id":"e_substitute",
        }],
        "pitfalls":[{
            "event_id":"e_pitfall",
            "typical_mistake":"只展开到二阶或误用大 O 三次余项",
            "correction":"至少展开到三阶，保留小 o 三次方余项",
            "spoken_mistake":"如果只展开到二次项，低阶项消掉以后，就找不到三次项的系数。",
            "spoken_correction":"所以必须展开到三阶。",
        }],
        "conclusion":{
            "event_id":"e_conclusion",
            "spoken_result":"L 等于三分之一。",
        },
        "recap":{
            "event_id":"e_summary",
            "spoken_recap":"最后归纳一下。这道题的关键是掌握自然对数的三阶泰勒展开。",
        },
    }
    spoken={
        "schema_version":"1.0","mode":"verified_spoken_classroom",
        "teacher_reviewed":True,"source_flow_sha256":flow.source_sha256,
        "voice":"zh-CN-XiaoxiaoNeural","speech_rate":"+1%",
        "lesson_contract":lesson_contract,"events":events,
    }
    (root/"spoken_classroom.json").write_text(
        json.dumps(spoken,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    assert checked_spoken(root/"spoken_classroom.json",adaptive=False)
    return spoken


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print("FRESH_LOG_LIMIT_VERIFIED_EVENTS",len(build(args.output)["events"]))
