"""Independent second, teacher-authored lesson after the 2.4 classroom redesign.

Unlike the original 3-addend integral, this item is a single integration-by-
parts question requiring algebraic division and an explicit return to the
original integral. Teaching rationale is designed *before* board animation.
No LLM was invoked and the preview does not claim audio/TTS synchronization.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from visual_director.director import build_storyboard
from animation_engine.planner import build_execution_plan

PROBLEM = r"求定积分：\int_0^1x^2\ln(1+x)\,\mathrm{d}x."
STEPS = [
 # (id, type, actual source formula, phase, short heading, explanation, pause)
 ("read","read_question",
  r"\int_0^1x^2\ln(1+x)\,\mathrm{d}x",
  "observe","先观察被积函数","这里是多项式与对数函数的乘积，先决定解题方法。",2.7),
 ("choice","orient",
  r"u=\ln(1+x),\ \mathrm{d}v=x^2\,\mathrm{d}x",
  "strategy","为什么选择分部积分","对数函数求导后更简单，多项式则容易积分。",2.7),
 ("parts","knowledge",
  r"\mathrm{d}u=\frac1{1+x}\,\mathrm{d}x,\ v=\frac{x^3}{3}",
  "knowledge","先写清楚各自的变化","求出两个函数的微分与原函数，再代入分部积分公式。",2.1),
 ("transform","application",
  r"I=\left[\frac{x^3}{3}\ln(1+x)\right]_0^1-\frac13\int_0^1\frac{x^3}{1+x}\,\mathrm{d}x",
  "application","把分部积分落实到本题","边界项与剩下的有理函数积分，分别处理。",2.5),
 ("define_j","derivation",
  r"J=\int_0^1\frac{x^3}{1+x}\,\mathrm{d}x",
  "strategy","先解决剩下的积分","把需要单独计算的有理函数积分记下来。",2.1),
 ("boundary","derivation",
  r"I=\frac{\ln2}{3}-\frac13J",
  "calculate","先化简边界项","代入上下限，原题转化为计算一个较简单的积分。",2.0),
 ("division","knowledge",
  r"\frac{x^3}{1+x}=x^2-x+1-\frac1{1+x}",
  "knowledge","关键是进行多项式除法","把分式变成多项式与简单分式，后续便能直接积分。",3.0),
 ("decompose","application",
  r"J=\int_0^1\left(x^2-x+1-\frac1{1+x}\right)\,\mathrm{d}x",
  "application","回到本题，替换被积函数","把刚才的恒等变形代入原来的辅助积分。",2.0),
 ("primitive","derivation",
  r"J=\left[\frac{x^3}{3}-\frac{x^2}{2}+x-\ln(1+x)\right]_0^1",
  "calculate","逐项写出原函数","多项式用幂函数积分，对数项来自简单分式。",2.8),
 ("bounds","derivation",
  r"J=\frac13-\frac12+1-\ln2",
  "calculate","完整代入积分上下限","先看上限得到的四个数，下限各项都为零。",2.1),
 ("jresult","derivation",
  r"J=\frac56-\ln2",
  "check","整理辅助积分的结果","常数项合并之后，记住这个值，稍后代回原题。",2.5),
 ("back","application",
  r"I=\frac{\ln2}{3}-\frac13\left(\frac56-\ln2\right)",
  "application","回到原题进行代入","用刚刚算出的辅助积分结果，替换原式里的辅助量。",2.8),
 ("expand","derivation",
  r"I=\frac{\ln2}{3}-\frac5{18}+\frac{\ln2}{3}",
  "calculate","展开括号，留意负号","外面的负三分之一同时乘进括号里的两个部分。",2.8),
 ("final","summary",
  r"I=\frac23\ln2-\frac5{18}",
  "summary","合并同类项得到答案","两个对数项相加，常数项保留，计算到这里结束。",3.5),
]

REFERENCE_SOLUTION = "\n".join([
    r"令 I=\int_0^1x^2\ln(1+x)\,\mathrm{d}x。",
    r"取 u=\ln(1+x)，\mathrm{d}v=x^2\,\mathrm{d}x，所以 \mathrm{d}u=\frac1{1+x}\,\mathrm{d}x，v=\frac{x^3}{3}。",
    r"分部积分得到 I=[\frac{x^3}{3}\ln(1+x)]_0^1-\frac13\int_0^1\frac{x^3}{1+x}\,\mathrm{d}x。",
    r"记 J=\int_0^1\frac{x^3}{1+x}\,\mathrm{d}x，因此 I=\frac{\ln2}{3}-\frac13J。",
    r"多项式除法：\frac{x^3}{1+x}=x^2-x+1-\frac1{1+x}。",
    r"J=\int_0^1(x^2-x+1-\frac1{1+x})\,\mathrm{d}x。",
    r"J=[\frac{x^3}{3}-\frac{x^2}{2}+x-\ln(1+x)]_0^1。",
    r"J=\frac13-\frac12+1-\ln2=\frac56-\ln2。",
    r"I=\frac{\ln2}{3}-\frac13(\frac56-\ln2)。",
    r"I=\frac{\ln2}{3}-\frac5{18}+\frac{\ln2}{3}=\frac23\ln2-\frac5{18}。",
])

def sha(value):
    return hashlib.sha256(json.dumps(
        value,sort_keys=True,ensure_ascii=False,separators=(",",":")
    ).encode("utf-8")).hexdigest()

def build():
    source = {
        "problem":PROBLEM,"reference_solution":REFERENCE_SOLUTION,
        "problem_segments":[{"source_id":"problem:0","text":PROBLEM,"kind":"problem"}],
        "solution_segments":[{"source_id":"solution:0","text":REFERENCE_SOLUTION,"kind":"solution"}],
    }
    teaching,lesson,objects,speech,board_actions,anims,captions=[],[],[],[],[],[],[]
    for i,(id,event_type,latex,phase,heading,note,pause) in enumerate(STEPS,1):
        event="e_"+id;mid="m_"+id;aid="b_"+id;uid="u_"+id;anim="a_"+id;step="s"+str(i)
        teaching.append({"event_id":event,"event_type":event_type,
          "source_step_ids":[step],"knowledge_binding_ids":[],
          "teaching_goal":heading+"："+note,
          "intended_board_content":[latex],
          "mathematical_progression":note})
        lesson.append({"event_id":event,"source_step_ids":[step],
                       "knowledge_binding_ids":[],"speech_unit_ids":[uid],
                       "board_action_ids":[aid],"animation_intent_ids":[anim]})
        objects.append({"math_object_id":mid,"latex":latex,"source_step_ids":[step]})
        # These are source-semantic speech units, NOT recorded speech.
        parts=[{"kind":"text","value":heading+"。"+note,"reading_intent":None},
               {"kind":"math","value":latex,
                "reading_intent":"规范数学读音由语音处理层决定"}]
        speech.append({"speech_unit_id":uid,"event_id":event,"parts":parts})
        board_actions.append({"board_action_id":aid,"event_id":event,
          "speech_unit_id":uid,"math_object_id":mid,
          "action":"highlight" if i==1 else "write","semantic_reason":note})
        anims.append({"animation_id":anim,"event_id":event,
          "speech_unit_ids":[uid],"board_action_ids":[aid],
          "mathematical_goal":note})
        captions.append({"subtitle_id":"subtitle:"+uid,"speech_unit_id":uid,
                         "parts":parts})
    pkg={"schema_version":"1.0","input_sha256":sha(source),
         "prompt_versions":{"global":"manually-audited-demo",
                            "A":"manual","B":"manual","C":"manual"},
         "source":source,"plan":{"teaching_events":teaching},
         "lesson":{"lesson_events":lesson,"math_objects":objects,
                   "speech_units":speech,"board_actions":board_actions,
                   "animation_intents":anims},
         "subtitles":captions,
         "validation":{"status":"ready_with_limits","issues":[],"math_checks":[]}}
    pkg["validated_content_sha256"]=sha(pkg)
    storyboard=build_storyboard(pkg)
    execution=build_execution_plan(storyboard)
    cues={"schema_version":"1.0",
          "source_storyboard_sha256":execution.source_storyboard_sha256,
          "events":[{"event_id":"e_"+id,"phase":phase,
                     "heading":heading,"detail":note,
                     "source_step_ids":["s"+str(i)],
                     "pause_seconds":pause,"write_seconds":1.25}
                    for i,(id,_,_,phase,heading,note,pause) in enumerate(STEPS,1)]}
    policy={
      "pinned_ids":[],"result_ids":["m_jresult"],
      "break_hints":{},"cut_before_events":[],
      "allow_scroll":True,"max_scrolls_per_page":2,
      "max_scroll_fraction":0.55,"carry_count":0,
      "full_width_without_diagram":True,"safe_auto_break":True,
      "content_top_offset_px":70,
      "board_mode":"simple_full_board",
      "board_column_width_px":660,
      "math_base_scale":0.78,
      "math_min_scale":0.72,
      "row_gap_px":11,
    }
    return pkg,storyboard,execution,cues,policy

def main(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    p,b,e,c,policy=build()
    files={
      "new_problem_and_solution.json":{"problem":PROBLEM,
                                       "reference_solution":REFERENCE_SOLUTION},
      "teaching_package.json":p,
      "storyboard.json":b.model_dump(mode="json"),
      "execution.json":e.model_dump(mode="json"),
      "teacher_approved_cues.json":c,
      "page_policy.json":policy,
    }
    for name,data in files.items():
        (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",
                                 encoding="utf-8")
    print("CLASSROOM_NEW_PROBLEM",len(STEPS),"teaching events from original teacher-authored steps")
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    main(parser.parse_args().output)
