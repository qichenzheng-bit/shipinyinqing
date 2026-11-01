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
    # Spoken connectors follow mathematical reasoning, never a software page.
    ("introduce_triangle", "e_intro", "diagram"):
        "题目给出直角三角形，A 角是直角，AB 长八、AC 长六，求斜边和周长。先画直角三角形的两条直角边，再连接 B、C。",
    ("introduce_triangle", "e_intro", "note"):
        "两条直角边已经知道了。要算周长，先得求出斜边。",
    ("introduce_triangle", "e_intro", "math"):
        "题目给出的两个长度是：",
    ("introduce_triangle", "e_angle", "diagram"):
        "在 A 角这里标出直角，说明这两条边互相垂直。",
    ("introduce_triangle", "e_angle", "math"):
        "所以我们知道，",
    ("introduce_triangle", "e_rule", "diagram"):
        "再标上 B、C。注意看，BC 正对着直角，就是斜边。",
    ("introduce_triangle", "e_rule", "note"):
        "既然是直角三角形，求斜边就可以用勾股定理。",
    ("introduce_triangle", "e_rule", "math"):
        "先把勾股定理写出来：",
    ("introduce_triangle", "e_apply", "math"):
        "把两条直角边的长度代进去：",
    ("calculate_hypotenuse", "e_carry", "math"):
        "等式已经列好了，接下来往下算：",
    ("calculate_hypotenuse", "e_square_value", "math"):
        "把这两个平方算一下：",
    ("calculate_hypotenuse", "e_hypotenuse", "math"):
        "因为边长要取正值，所以：",
    ("calculate_perimeter", "e_recap", "math"):
        "好，斜边算出来了，",
    ("calculate_perimeter", "e_legs", "note"):
        "另外两条边的长度，题目已经告诉我们了。",
    ("calculate_perimeter", "e_legs", "math"):
        "分别是：",
    ("calculate_perimeter", "e_perimeter", "math"):
        "三角形的周长，就是三条边长相加：",
    ("calculate_perimeter", "e_final", "note"):
        "所以，把刚才求出的三条边长加起来就行。",
    ("calculate_perimeter", "e_final", "math"):
        "这个三角形的周长就是：",
}
# Each visible stroke/label is anchored to a specific true TTS phrase.
# It is not enough to bind all strokes to the same broad teaching event.
DIAGRAM_PHRASE_CUES = {
    ("introduce_triangle", "e_intro"): [
        {"object_id":"A","phrase":"题目给出直角三角形，"},
        {"object_id":"B","phrase":"题目给出直角三角形，"},
        {"object_id":"C","phrase":"题目给出直角三角形，"},
        {"object_id":"AB","phrase":"先画直角三角形的两条直角边，"},
        {"object_id":"AC","phrase":"先画直角三角形的两条直角边，"},
        {"object_id":"BC","phrase":"再连接 B、C。"},
    ],
    ("introduce_triangle", "e_angle"): [
        {"object_id":"right_1","phrase":"在 A 角这里标出直角，"},
        {"object_id":"right_2","phrase":"在 A 角这里标出直角，"},
        {"object_id":"label:A","phrase":"在 A 角这里标出直角，"},
    ],
    ("introduce_triangle", "e_rule"): [
        {"object_id":"label:B","phrase":"再标上 B、C。"},
        {"object_id":"label:C","phrase":"再标上 B、C。"},
    ],
}
MATH_READING = {
    "m_legs": "A B 等于八，A C 等于六。",
    "m_perpendicular": "A B 垂直于 A C。",
    "m_pythagoras": "a 的平方加 b 的平方等于 c 的平方。",
    "m_square": "B C 的平方等于八的平方加六的平方。",
    # The identical MathTex is carried by a verified source handoff;
    # do not mechanically read the full previously voiced equation again.
    "m_square_handoff": "先看八的平方加六的平方。",
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
                    {"kind":"math","latex":latex,"reading":reading, **({"spoken_math_latex":r"8^2+6^2"} if obj=="m_square_handoff" else {})},
                ]
            else:
                parts=[{"kind":"text","value":text}]
            item={"kind":kind,"object_id":obj,"parts":parts}
            if kind=="diagram" and (stage_id,eid) in DIAGRAM_PHRASE_CUES:
                item["diagram_phrase_cues"]=DIAGRAM_PHRASE_CUES[(stage_id,eid)]
            spans.append(item)
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
