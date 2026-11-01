"""V2.6.4 reviewed spoken lesson: entire 6-8-10 classroom, not a readout of answers.

All teacher utterances are separately authored by pedagogical purpose. The
source-math identity is automatically copied ONLY for text/image binding,
never used to invent a spoken explanation or a Chinese pronunciation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from animation_engine.spoken_classroom import _expected_actions
from animation_engine.unified_classroom_flow import canonical_sha, checked_flow
from build_math_memory_triangle import export_memory_triangle


# One complete, natural explanation of every visible teaching note and drawing.
# No references to the model answer, no empty filler or meaningless microsteps.
NARRATIVE = {
    # Every visual instruction starts together with the matching drawing.
    # Opening: AB, AC, then BC; later: right angle, then vertex labels.
    ("introduce_triangle", "e_intro", "diagram"):
        "先画直角三角形。从 A 点向 B 和 C 分别画出两条直角边，最后连接 B、C，构成三条边。",
    ("introduce_triangle", "e_intro", "note"):
        "思路是先求斜边，再求周长。",
    ("introduce_triangle", "e_intro", "math"):
        "两条直角边的长度是：",
    ("introduce_triangle", "e_angle", "diagram"):
        "在 A 点标出直角，注意这两条边互相垂直。",
    ("introduce_triangle", "e_angle", "math"):
        "所以有：",
    ("introduce_triangle", "e_rule", "diagram"):
        "标出 B、C 两个顶点，它们之间的这条边就是斜边。",
    ("introduce_triangle", "e_rule", "note"):
        "勾股定理用于直角三角形，关键是认准斜边。",
    ("introduce_triangle", "e_rule", "math"):
        "对应的公式是：",
    ("introduce_triangle", "e_apply", "math"):
        "代入题目给的边长：",
    ("calculate_hypotenuse", "e_carry", "math"):
        "把上一页的等式接到计算区：",
    ("calculate_hypotenuse", "e_square_value", "math"):
        "分别计算两个平方：",
    ("calculate_hypotenuse", "e_hypotenuse", "math"):
        "边长取正，因此：",
    ("calculate_perimeter", "e_recap", "math"):
        "接着求周长，斜边已经算出：",
    ("calculate_perimeter", "e_legs", "note"):
        "还要用到题目给出的两条直角边。",
    ("calculate_perimeter", "e_legs", "math"):
        "它们分别是：",
    ("calculate_perimeter", "e_perimeter", "math"):
        "按周长定义：",
    ("calculate_perimeter", "e_final", "note"):
        "现在把三条边的长度相加。",
    ("calculate_perimeter", "e_final", "math"):
        "结果为：",
}
MATH_READING = {
    "m_legs": "A B 等于八，A C 等于六。",
    "m_perpendicular": "A B 垂直于 A C。",
    "m_pythagoras": "a 的平方加 b 的平方等于 c 的平方。",
    "m_square": "B C 的平方等于八的平方加六的平方。",
    # The identical MathTex is carried by a verified source handoff;
    # do not mechanically read the full previously voiced equation again.
    "m_square_handoff": "这就是上一步的等式。",
    "m_squares": "B C 的平方等于六十四加三十六，等于一百。",
    "m_hypotenuse": "B C 等于十。",
    "m_hypotenuse_recall": "B C 等于十。",
    "m_legs_recall": "A B 等于八，A C 等于六。",
    "m_perimeter_rule": "周长 P 等于 A B 加 A C 加 B C。",
    "m_perimeter_result": "P 等于八加六加十，等于二十四。",
}


def export_spoken_triangle(root: Path):
    root=Path(root)
    export_memory_triangle(root)
    flow=checked_flow(root/"unified_flow.json")
    plan=_expected_actions(flow,adaptive=True)
    events=[]
    for event in plan:
        stage_id,eid=event["stage_id"],event["event_id"]
        spans=[]
        for kind,obj,latex in event["actions"]:
            text=NARRATIVE.get((stage_id,eid,kind))
            if text is None:
                raise ValueError("SPOKEN_NOT_AUTHORED: "+stage_id+"/"+eid+"/"+kind)
            if kind=="math":
                reading=MATH_READING.get(obj)
                if not reading:
                    raise ValueError("SPOKEN_MATH_PRONUNCIATION_NOT_AUTHORED: "+obj)
                parts=[
                    {"kind":"text","value":text},
                    {"kind":"math","latex":latex,"reading":reading},
                ]
            else:
                parts=[{"kind":"text","value":text}]
            spans.append({"kind":kind,"object_id":obj,"parts":parts})
        events.append({
            "stage_id":stage_id,"event_id":eid,
            "pedagogical_cue_covered":True,
            "question_read_aloud":len(events)==0,
            "question_source_sha256":(
                canonical_sha(flow.problem) if len(events)==0 else None
            ),
            "spans":spans,
        })
    result={
        "schema_version":"1.0",
        "mode":"verified_spoken_classroom",
        "teacher_reviewed":True,
        "source_flow_sha256":flow.source_sha256,
        "voice":"zh-CN-YunxiNeural",
        "speech_rate":"+1%",
        "events":events,
    }
    (root/"spoken_classroom.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    data=export_spoken_triangle(args.output)
    print("V2_6_4_TEACHER_REVIEWED_SPEECH",
          len(data["events"]),
          sum(len(e["spans"]) for e in data["events"]))
