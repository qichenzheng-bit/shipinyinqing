"""Fresh, human-authored end-to-end fixture for 2.4, not the legacy limit example.

The source problem and detailed answer were independently chosen for the
longboard acceptance. This is NOT a claim that a live LLM teacher model ran:
the fixture is an explicitly authored TeachingPackage-like contract. It is
validated by the actual visual-director and animation ExecutionPlan pipeline.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from visual_director.director import build_storyboard
from animation_engine.planner import build_execution_plan


PROBLEM = (
    r"求积分：\int_0^1\left(xe^{x^2}+x\ln(1+x^2)+x^2\right)\,\mathrm{d}x."
)
STEPS = [
    ("read", "read_question", r"\int_0^1\left(xe^{x^2}+x\ln(1+x^2)+x^2\right)\,\mathrm{d}x",
     "先读题。被积函数是三项之和，适合先拆开分别计算。"),
    ("split", "derivation", r"I=I_1+I_2+I_3",
     "根据积分的线性性质，我们把原积分拆成三项，每项独立计算，最后再相加。"),
    ("a0", "derivation", r"I_1=\int_0^1xe^{x^2}\,\mathrm{d}x",
     "第一项是 x 乘以 e 的 x 平方次方，适合对 x 的平方进行换元。"),
    ("a_sub", "knowledge", r"u=x^2,\quad \mathrm{d}u=2x\,\mathrm{d}x",
     "令 u 等于 x 平方，则 d u 等于二 x d x，上下限依次为零和一。"),
    ("a1", "application", r"I_1=\frac12\int_0^1e^u\,\mathrm{d}u",
     "将 x d x 替换为 d u 的二分之一，得二分之一乘以零到一的 e 的 u 次方积分。"),
    ("a2", "derivation", r"I_1=\frac12[e^u]_0^1",
     "e 的 u 次方原函数仍为 e 的 u 次方，然后代入上下限。"),
    ("a_done", "derivation", r"I_1=\frac{e-1}{2}",
     "因此第一项计算结果为 e 减一再除以二。"),
    ("b0", "derivation", r"I_2=\int_0^1x\ln(1+x^2)\,\mathrm{d}x",
     "第二项包含 ln 一加 x 平方，也采用换元法。"),
    ("b_sub", "knowledge", r"t=1+x^2,\quad \mathrm{d}t=2x\,\mathrm{d}x",
     "令 t 为一加 x 平方，d t 等于二 x d x，新的积分区间是一到二。"),
    ("b1", "application", r"I_2=\frac12\int_1^2\ln t\,\mathrm{d}t",
     "换元后得到二分之一乘以一到二的 ln t 积分。"),
    ("b_parts", "knowledge", r"\int\ln t\,\mathrm{d}t=t\ln t-t+C",
     "对 ln t 使用分部积分，取 u 为 ln t、d v 为 d t，原函数是 t ln t 减 t。"),
    ("b2", "derivation", r"I_2=\frac12[t\ln t-t]_1^2",
     "写出原函数，代入上限二和下限一。"),
    ("b3", "derivation", r"I_2=\frac12(2\ln2-2+1)",
     "上限得到二 ln 二减二，下限得到负一，所以减去下限是加一。"),
    ("b_done", "derivation", r"I_2=\ln2-\frac12",
     "合并得到第二项 ln 二减去二分之一。"),
    ("c0", "derivation", r"I_3=\int_0^1x^2\,\mathrm{d}x",
     "第三项是基本的幂函数积分。"),
    ("c1", "derivation", r"I_3=[\frac{x^3}{3}]_0^1",
     "其原函数为 x 三次方除以三，代入积分上下限。"),
    ("c_done", "derivation", r"I_3=\frac13",
     "所以第三项的结果是三分之一。"),
    ("summary", "summary", r"I=I_1+I_2+I_3",
     "三个积分都已算出，现在回到最开始的拆项式。"),
    ("substitution", "derivation",
     r"I=\frac{e-1}{2}+\ln2-\frac12+\frac13",
     "依次代入三项结果，保持每一项的符号与数值不变。"),
    ("final", "summary", r"I=\frac e2+\ln2-\frac23",
     "合并常数，最终答案为二分之 e 加 ln 二减三分之二。"),
]

REFERENCE_SOLUTION = "\n".join([
    r"设 I=\int_0^1(xe^{x^2}+x\ln(1+x^2)+x^2)\,\mathrm{d}x=I_1+I_2+I_3。",
    r"第一项令 u=x^2，\mathrm{d}u=2x\,\mathrm{d}x，上下限仍为0和1。",
    r"I_1=\frac12\int_0^1e^u\,\mathrm{d}u=\frac12[e^u]_0^1=\frac{e-1}{2}。",
    r"第二项令 t=1+x^2，\mathrm{d}t=2x\,\mathrm{d}x，上下限变为1和2。",
    r"I_2=\frac12\int_1^2\ln t\,\mathrm{d}t。",
    r"分部积分：\int\ln t\,\mathrm{d}t=t\ln t-t+C。",
    r"I_2=\frac12[t\ln t-t]_1^2=\frac12(2\ln2-2+1)=\ln2-\frac12。",
    r"I_3=\int_0^1x^2\,\mathrm{d}x=[\frac{x^3}{3}]_0^1=\frac13。",
    r"I=I_1+I_2+I_3=\frac{e-1}{2}+\ln2-\frac12+\frac13=\frac e2+\ln2-\frac23。",
])

def stable_sha(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def make_package():
    source = {
        "problem": PROBLEM, "reference_solution": REFERENCE_SOLUTION,
        "problem_segments": [{"source_id": "problem:0",
                              "text": PROBLEM, "kind": "problem"}],
        "solution_segments": [{"source_id": "solution:0",
                               "text": REFERENCE_SOLUTION, "kind": "solution"}],
    }
    teacher_events, lesson_events, math_objects = [], [], []
    speech_units, actions, animation_intents, captions = [], [], [], []
    for i, (eid, etype, latex, spoken) in enumerate(STEPS, start=1):
        event_id, object_id = "e_"+eid, "m_"+eid
        speech_id, action_id, animation_id = "u_"+eid, "b_"+eid, "a_"+eid
        step_id = "s"+str(i)
        teacher_events.append({
            "event_id": event_id, "event_type":etype,
            "source_step_ids":[step_id], "knowledge_binding_ids":[],
            "teaching_goal":spoken,
            "intended_board_content":[latex],
            "mathematical_progression": spoken,
        })
        lesson_events.append({
            "event_id":event_id, "source_step_ids":[step_id],
            "knowledge_binding_ids":[],
            "speech_unit_ids":[speech_id],
            "board_action_ids":[action_id],
            "animation_intent_ids":[animation_id],
        })
        math_objects.append({
            "math_object_id":object_id, "latex":latex, "source_step_ids":[step_id],
        })
        parts = [
            {"kind":"text", "value": spoken, "reading_intent":None},
            {"kind":"math", "value":latex,
             "reading_intent":"按数学规范阅读，显示文本仍保留原 LaTeX"},
        ]
        speech_units.append({
            "speech_unit_id":speech_id,"event_id":event_id,"parts":parts,
        })
        actions.append({
            "board_action_id":action_id,
            "event_id":event_id,
            "speech_unit_id":speech_id,
            "math_object_id":object_id,
            "action":"highlight" if i==1 else "write",
            "semantic_reason":spoken,
        })
        animation_intents.append({
            "animation_id":animation_id, "event_id":event_id,
            "speech_unit_ids":[speech_id], "board_action_ids":[action_id],
            "mathematical_goal":spoken,
        })
        captions.append({
            "subtitle_id":"subtitle:"+speech_id,"speech_unit_id":speech_id,
            "parts":parts,
        })
    package={
        "schema_version":"1.0",
        "prompt_versions":{"global":"manual-independent-acceptance",
                           "A":"manual","B":"manual","C":"manual"},
        "input_sha256":stable_sha(source),
        "source":source,
        "understanding":{
            "reference_method":"分项积分；指数型换元；对数换元与分部积分；幂积分",
            "solution_structure":"拆分三个积分→分别计算→合并",
        },
        "plan":{"teaching_events":teacher_events,
                "teaching_strategy":"适度精讲，每项计算不跳步"},
        "lesson":{
            "lesson_events":lesson_events,
            "math_objects":math_objects,
            "speech_units":speech_units,
            "board_actions":actions,
            "animation_intents":animation_intents,
        },
        "subtitles":captions,
        "validation":{"status":"ready_with_limits",
                      "issues":[],
                      "math_checks":[],
                      "note":"Manual independently audited fixture; not generated by live model"},
    }
    package["validated_content_sha256"]=stable_sha(package)
    return package


def main(folder):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    package=make_package()
    (folder/"fresh_question_and_solution.json").write_text(
        json.dumps({"problem":PROBLEM,"reference_solution":REFERENCE_SOLUTION},
                   ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    (folder/"fresh_teaching_package.json").write_text(
        json.dumps(package,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    board=build_storyboard(package)
    execution=build_execution_plan(board)
    (folder/"storyboard.json").write_text(board.model_dump_json(indent=2)+"\n")
    (folder/"execution.json").write_text(execution.model_dump_json(indent=2)+"\n")
    print("FRESH_LESSON", len(STEPS), "approved math events and all source contracts generated")


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    main(parser.parse_args().output)
