"""New, independent postgraduate calculus limit lesson.

Unlike either earlier integral test, this proves a fifth-order Taylor limit
from sine/cosine and a reciprocal expansion. All steps are separately written,
mathematically authored and independently verified with SymPy in CI.
This program reuses the generic source-to-package builder, NOT its math.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import build_classroom_rework_example as scaffold
from animation_engine.classroom_policy import simple_classroom_policy

PROBLEM=(
    r"求极限：\lim_{x\to0}\frac{\tan x-\sin x-\frac{x^3}{2}}{x^5}."
)
STEPS=[
 ("read","read_question",
  r"L=\lim_{x\to0}\frac{\tan x-\sin x-\frac{x^3}{2}}{x^5}",
  "observe","先看分母的阶数",
  "分母是五次幂，应判断分子经过抵消后最先剩下哪一阶。",2.5),
 ("choice","orient",
  r"\tan x=\frac{\sin x}{\cos x}",
  "strategy","先把正切函数转化",
  "正切由正弦和余弦组成，分别展开就能算出所需的高阶项。",2.4),
 ("sine","knowledge",
  r"\sin x=x-\frac{x^3}{6}+\frac{x^5}{120}+o(x^5)",
  "knowledge","先写正弦的五阶展开",
  "正弦展开包含一次项三次项和五次项，此题需要保留五次项。",2.7),
 ("cosine","derivation",
  r"\cos x=1-\frac{x^2}{2}+\frac{x^4}{24}+o(x^4)",
  "calculate","写出余弦的四阶展开",
  "后面要计算正切，因此还需要余弦函数的倒数。",2.1),
 ("reciprule","knowledge",
  r"\frac1{1+u}=1-u+u^2+o(u^2)",
  "knowledge","倒数可以用展开公式",
  "余弦接近一，使用倒数展开能避免复杂的多项式长除法。",2.5),
 ("setu","application",
  r"u=-\frac{x^2}{2}+\frac{x^4}{24}+o(x^4)",
  "application","对应代入余弦的部分",
  "把余弦减去一后剩下的部分代入倒数展开式。",2.0),
 ("usquared","derivation",
  r"u^2=\frac{x^4}{4}+o(x^4)",
  "calculate","先算平方项的阶数",
  "只要保留四次项，其余更高阶项此时都可以合并。",2.0),
 ("reciprocal","derivation",
  r"\frac1{\cos x}=1+\frac{x^2}{2}+\frac{5x^4}{24}+o(x^4)",
  "calculate","合并得到余弦的倒数",
  "代回前面的展开并合并二次项和四次项。",2.7),
 ("product","application",
  r"\tan x=\sin x\cdot\frac1{\cos x}",
  "application","接着计算正切的展开",
  "正切就是刚才得到的正弦展开乘上余弦倒数展开。",2.1),
 ("cubic","derivation",
  r"\frac12-\frac16=\frac13",
  "calculate","整理三次项的系数",
  "三次项由一次项乘二次项以及原来的三次项相加得到。",2.0),
 ("quintic","derivation",
  r"\frac5{24}-\frac1{12}+\frac1{120}=\frac2{15}",
  "calculate","整理五次项的系数",
  "五次项来自三种乘积，分别计算后再合并。",2.5),
 ("tanexp","derivation",
  r"\tan x=x+\frac{x^3}{3}+\frac{2x^5}{15}+o(x^5)",
  "check","写出完整的正切展开",
  "三次项和五次项都已算清，现在可以与正弦展开作差。",2.5),
 ("pitfall","knowledge",
  r"\frac13+\frac16-\frac12=0",
  "pitfall","注意三次项会完全抵消",
  "如果只算到三次项就结束，会错过真正决定极限的五次项。",2.8),
 ("subtract","application",
  r"\tan x-\sin x=\frac{x^3}{2}+\left(\frac2{15}-\frac1{120}\right)x^5+o(x^5)",
  "application","按同次幂逐项相减",
  "一次项相消，剩下三次项以及需要精确计算的五次项。",2.8),
 ("coefficient","derivation",
  r"\frac2{15}-\frac1{120}=\frac18",
  "calculate","合并五次项的系数",
  "通分后相减，得到五次项的准确系数。",2.0),
 ("numerator","derivation",
  r"\tan x-\sin x-\frac{x^3}{2}=\frac{x^5}{8}+o(x^5)",
  "calculate","最后消去三次项",
  "题目分子恰好减去了三次项，因此只剩五次项和高阶小量。",2.6),
 ("limitsub","application",
  r"L=\lim_{x\to0}\left(\frac18+\frac{o(x^5)}{x^5}\right)",
  "application","除以分母的五次幂",
  "把分子表达式整体除以五次幂，再分别观察两项。",2.5),
 ("littleo","knowledge",
  r"\lim_{x\to0}\frac{o(x^5)}{x^5}=0",
  "knowledge","高阶小量的定义",
  "高阶小量除以对应的五次幂后趋于零。",2.2),
 ("final","summary",
  r"L=\frac18",
  "summary","归纳这道题的思路",
  "先找到抵消后所需的阶数，再展开到该阶并准确合并系数。",3.5),
]
REFERENCE_SOLUTION="\n".join([
  r"设 L=\lim_{x\to0}\frac{\tan x-\sin x-\frac{x^3}{2}}{x^5}。",
  r"已知 \sin x=x-\frac{x^3}{6}+\frac{x^5}{120}+o(x^5)，\cos x=1-\frac{x^2}{2}+\frac{x^4}{24}+o(x^4)。",
  r"利用 \frac1{1+u}=1-u+u^2+o(u^2)，令 u=-\frac{x^2}{2}+\frac{x^4}{24}+o(x^4)，则 u^2=\frac{x^4}{4}+o(x^4)。",
  r"所以 \frac1{\cos x}=1+\frac{x^2}{2}+\frac{5x^4}{24}+o(x^4)。",
  r"\tan x=\sin x/\cos x=x+\frac{x^3}{3}+\frac{2x^5}{15}+o(x^5)，其中五次项系数为 \frac5{24}-\frac1{12}+\frac1{120}=\frac2{15}。",
  r"\tan x-\sin x=\frac{x^3}{2}+\left(\frac2{15}-\frac1{120}\right)x^5+o(x^5)=\frac{x^3}{2}+\frac{x^5}{8}+o(x^5)。",
  r"\tan x-\sin x-\frac{x^3}{2}=\frac{x^5}{8}+o(x^5)，所以 L=\frac18。",
])


def build_new():
    # The generic function only assembles source-verified event contracts;
    # every actual mathematical expression above is independent and new.
    scaffold.PROBLEM=PROBLEM
    scaffold.STEPS=STEPS
    scaffold.REFERENCE_SOLUTION=REFERENCE_SOLUTION
    pkg,board,execution,cues,_=scaffold.build()
    policy=simple_classroom_policy(result_ids=("m_final",))
    return pkg,board,execution,cues,policy


def main(output:Path):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    pkg,board,execution,cues,policy=build_new()
    data={
      "problem_and_reference_solution.json":{
          "problem":PROBLEM,"solution":REFERENCE_SOLUTION,
          "expected_limit":"1/8","source_type":"new_teacher_authored"},
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
    print("FRESH_TAYLOR_LIMIT_LESSON",len(STEPS),"events; no audio")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True,type=Path)
    main(p.parse_args().output)
