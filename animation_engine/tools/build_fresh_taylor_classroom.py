"""Reworked Taylor limit lesson: complete derivations, not 19 pseudo-lessons.

The earlier demonstration split individual coefficients into separate teacher
events and omitted the multiplication that produced them. Five meaningful
pedagogical goals now contain the entire calculation; all display math is
source-approved MathTex and there are no unnecessary standalone steps.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy


PROBLEM=(
    r"求极限：\lim_{x\to0}\frac{\tan x-\sin x-\frac{x^3}{2}}{x^5}."
)
REFERENCE_SOLUTION="\n".join([
    r"先把正切与正弦合并：\tan x-\sin x=\sin x(1-\cos x)/\cos x。",
    r"展开：\sin x=x-\frac{x^3}{6}+o(x^3)，",
    r"1-\cos x=\frac{x^2}{2}-\frac{x^4}{24}+o(x^4)，",
    r"\frac1{\cos x}=1+\frac{x^2}{2}+o(x^2)。",
    r"逐项相乘：\sin x(1-\cos x)"
    r"=(x-\frac{x^3}{6})(\frac{x^2}{2}-\frac{x^4}{24})+o(x^5)"
    r"=\frac{x^3}{2}-\frac{x^5}{24}-\frac{x^5}{12}+o(x^5)"
    r"=\frac{x^3}{2}-\frac{x^5}{8}+o(x^5)。",
    r"所以 \tan x-\sin x="
    r"(\frac{x^3}{2}-\frac{x^5}{8})(1+\frac{x^2}{2})+o(x^5)"
    r"=\frac{x^3}{2}+(\frac14-\frac18)x^5+o(x^5)"
    r"=\frac{x^3}{2}+\frac{x^5}{8}+o(x^5)。",
    r"再减去题目给出的三次项，得"
    r"\tan x-\sin x-\frac{x^3}{2}=\frac{x^5}{8}+o(x^5)，"
    r"极限等于 \frac18。",
])

UNITS=[
  {"id":"structure","event_type":"orient","phase":"strategy",
   "heading":"先把差式化为乘积",
   "detail":"合并正切与正弦，观察乘积中哪些阶数将决定最后结果。",
   "goal":"通过恒等变形确定分子主要阶数，避免盲目展开正切。",
   "pause_seconds":2.4,"write_seconds":1.1,
   "math":[
      {"id":"identity",
       "latex":r"\tan x-\sin x=\frac{\sin x(1-\cos x)}{\cos x}",
       "reason":"使用正切等于正弦除余弦，直接取得可控乘积结构。"},
   ]},
  {"id":"expansions","event_type":"knowledge","phase":"knowledge",
   "heading":"只展开到需要的阶",
   "detail":"分母是五次幂，三个因子按乘积阶数分别保留足够的项。",
   "goal":"说明正弦保留三次、余弦差保留四次、倒数保留二次。",
   "pause_seconds":2.4,"write_seconds":1.0,
   "math":[
      {"id":"sin",
       "latex":r"\sin x=x-\frac{x^3}{6}+o(x^3)",
       "reason":"正弦乘至少二次因子，保留到三次便足够。"},
      {"id":"cosdiff",
       "latex":r"1-\cos x=\frac{x^2}{2}-\frac{x^4}{24}+o(x^4)",
       "reason":"与正弦一次项相乘，四次项正好影响五次项。"},
      {"id":"invcos",
       "latex":r"\frac1{\cos x}=1+\frac{x^2}{2}+o(x^2)",
       "reason":"被乘积前三次项所乘，倒数只需二次项。"},
   ]},
  {"id":"product","event_type":"derivation","phase":"application",
   "heading":"展开两个函数的乘积",
   "detail":"五次项分别来自一次乘四次，以及三次乘二次，不省略这步计算。",
   "goal":"完整写出产生五次项的两个来源并合并系数。",
   "pause_seconds":2.6,"write_seconds":1.0,
   "math":[
      {"id":"product_substitution",
       "latex":r"\sin x(1-\cos x)=(x-\frac{x^3}{6})(\frac{x^2}{2}-\frac{x^4}{24})+o(x^5)",
       "reason":"先把两种泰勒展开代入乘积式，准确保留余项。"},
      {"id":"product_terms",
       "latex":r"=\frac{x^3}{2}-\frac{x^5}{24}-\frac{x^5}{12}+o(x^5)",
       "reason":"展示一次乘四次和三次乘二次各自得到的五次项。"},
      {"id":"product_result",
       "latex":r"=\frac{x^3}{2}-\frac{x^5}{8}+o(x^5)",
       "reason":"合并两个五次项，得到分子的核心中间结果。"},
   ]},
  {"id":"quotient","event_type":"derivation","phase":"application",
   "heading":"再乘余弦函数倒数",
   "detail":"只保留影响五次项的乘积，并把三次项与五次项分别合并。",
   "goal":"从中间乘积推导出正切与正弦差式的完整五阶展开。",
   "pause_seconds":2.5,"write_seconds":1.0,
   "math":[
      {"id":"quotient_substitution",
       "latex":r"\tan x-\sin x=(\frac{x^3}{2}-\frac{x^5}{8})(1+\frac{x^2}{2})+o(x^5)",
       "reason":"代入余弦的倒数并展示乘法关系。"},
      {"id":"quotient_terms",
       "latex":r"=\frac{x^3}{2}+(\frac14-\frac18)x^5+o(x^5)",
       "reason":"明确五次项除了原乘积项，还来自三次项乘二次项。"},
      {"id":"quotient_result",
       "latex":r"=\frac{x^3}{2}+\frac{x^5}{8}+o(x^5)",
       "reason":"合并五次项，为题目减去三次项做好准备。"},
   ]},
  {"id":"conclusion","event_type":"summary","phase":"pitfall",
   "heading":"三次项必须准确抵消",
   "detail":"题目减去了整个三次项，剩余五次项才决定极限，不能提前停止。",
   "goal":"展示三次项消去与小量除法，不将最终答案变成无依据孤立数字。",
   "pause_seconds":2.8,"write_seconds":1.0,
   "math":[
      {"id":"numerator",
       "latex":r"\tan x-\sin x-\frac{x^3}{2}=\frac{x^5}{8}+o(x^5)",
       "reason":"代入实际题目，三次项完整抵消，仅剩五次项。"},
      {"id":"final",
       "latex":r"L=\lim_{x\to0}(\frac18+\frac{o(x^5)}{x^5})=\frac18",
       "reason":"利用高阶小量定义得到最终极限。"},
   ]},
]
# Legacy callers may still inspect STEPS; these are now complete teaching
# UNITS, not one-formula pseudo-events.
STEPS=UNITS


def build_new():
    pkg,board,execution,cues=compile_teaching_units(
        problem=PROBLEM,reference_solution=REFERENCE_SOLUTION,units=UNITS
    )
    policy=simple_classroom_policy(result_ids=("m_final",))
    return pkg,board,execution,cues,policy


def main(output:Path):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    pkg,board,execution,cues,policy=build_new()
    data={
       "problem_and_reference_solution.json":{
           "problem":PROBLEM,"solution":REFERENCE_SOLUTION,
           "expected_limit":"1/8","source_type":"teacher-authored-revised",
           "unit_count":len(UNITS),
           "formula_write_count":sum(len(u["math"]) for u in UNITS)},
       "teaching_units.json":{"schema_version":"1.0","units":UNITS},
       "teaching_package.json":pkg,
       "storyboard.json":board.model_dump(mode="json"),
       "execution.json":execution.model_dump(mode="json"),
       "teacher_approved_cues.json":cues,
       "page_policy.json":policy,
    }
    for name,value in data.items():
        (output/name).write_text(
            json.dumps(value,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8"
        )
    print("REVISED_TAYLOR_COMPLETE_UNITS",len(UNITS),
          "MATH_WRITES",sum(len(u["math"]) for u in UNITS),
          "no isolated coefficient pseudo-events")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    main(parser.parse_args().output)
