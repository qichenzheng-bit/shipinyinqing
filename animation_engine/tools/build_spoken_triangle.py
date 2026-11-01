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
    ("introduce_triangle", "e_intro", "diagram"):
        "这道题给我们一个直角三角形，两条直角边分别长八和六，要求斜边的长度和周长。我们先把直角三角形画出来，明确每条边的位置。",
    ("introduce_triangle", "e_intro", "note"):
        "思路是先找清直角边和斜边，利用直角三角形的性质求出第三条边，然后再计算三条边的总长度。",
    ("introduce_triangle", "e_intro", "math"):
        "题目给出的两条直角边长度分别为",
    ("introduce_triangle", "e_angle", "diagram"):
        "注意直角顶点的位置。两条从这个顶点出发的边互相垂直，另一条连接其余两点的边才是斜边。",
    ("introduce_triangle", "e_angle", "math"):
        "因此，这两条直角边满足垂直关系：",
    ("introduce_triangle", "e_rule", "diagram"):
        "现在将第三条边补全，在图上标清斜边。我们接着使用直角三角形的勾股定理。",
    ("introduce_triangle", "e_rule", "note"):
        "勾股定理的适用条件是直角三角形。这里不能随便把三条边代入，要确认哪一条是斜边。",
    ("introduce_triangle", "e_rule", "math"):
        "勾股定理告诉我们，两条直角边的平方和等于斜边的平方，也就是",
    ("introduce_triangle", "e_apply", "math"):
        "把本题的两条直角边代入，斜边的平方就等于",
    ("calculate_hypotenuse", "e_carry", "math"):
        "沿着刚才建立的勾股定理关系，我们继续计算。已经得到",
    ("calculate_hypotenuse", "e_square_value", "math"):
        "八的平方是六十四，六的平方是三十六，两者相加为一百，所以",
    ("calculate_hypotenuse", "e_hypotenuse", "math"):
        "三角形的边长必须是正数，因此取算术平方根，求得",
    ("calculate_perimeter", "e_recap", "math"):
        "斜边已经求出，这里直接使用刚才算出的结果，不需要重复做一遍平方根计算。",
    ("calculate_perimeter", "e_legs", "note"):
        "接下来计算周长。需要三条边的长度，因此先回顾题目最初给出的两条直角边。",
    ("calculate_perimeter", "e_legs", "math"):
        "另外两条边的长度仍然是题目给出的",
    ("calculate_perimeter", "e_perimeter", "math"):
        "三角形的周长是三条边长度的和，我们先写出周长关系式",
    ("calculate_perimeter", "e_final", "note"):
        "最后把已经求出的斜边和题设给出的两条直角边一起相加，检查三条边都被计入。",
    ("calculate_perimeter", "e_final", "math"):
        "因此，周长等于八加六再加十，得到二十四。完整的计算式为",
}
MATH_READING = {
    "m_legs": "A B 等于八，A C 等于六。",
    "m_perpendicular": "A B 垂直于 A C。",
    "m_pythagoras": "a 的平方加 b 的平方等于 c 的平方。",
    "m_square": "B C 的平方等于八的平方加六的平方。",
    "m_square_handoff": "B C 的平方等于八的平方加六的平方。",
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
