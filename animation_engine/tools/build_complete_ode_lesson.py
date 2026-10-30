"""Third independent classroom acceptance topic: first-order ODE initial value.

No integral/Taylor demonstration is reused. Four meaningful teaching units,
each carrying the complete related multi-line mathematical derivation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy


PROBLEM=(
    r"解初值问题：\begin{cases}y'+2xy=2x,\\y(0)=0.\end{cases}"
)

REFERENCE_SOLUTION="\n".join([
    r"考虑一阶线性微分方程 y'+2xy=2x，y(0)=0。",
    r"积分因子为 \mu(x)=\exp(\int2x\,\mathrm{d}x)=e^{x^2}。",
    r"两边乘积分因子得 e^{x^2}y'+2xe^{x^2}y=2xe^{x^2}。",
    r"根据乘积求导公式 (ye^{x^2})'=e^{x^2}y'+2xe^{x^2}y，故 (ye^{x^2})'=2xe^{x^2}。",
    r"积分可得 ye^{x^2}=\int2xe^{x^2}\,\mathrm{d}x=e^{x^2}+C。",
    r"解得 y=1+Ce^{-x^2}；代入 y(0)=0，得 0=1+C，所以 C=-1。",
    r"因此 y=1-e^{-x^2}；验证 y'=2xe^{-x^2}，",
    r"y'+2xy=2xe^{-x^2}+2x(1-e^{-x^2})=2x，且 y(0)=1-e^0=0。",
])

UNITS=[
  {
    "id":"method","event_type":"orient","phase":"strategy",
    "heading":"先决定求解方法",
    "detail":"这是标准的一阶线性方程，积分因子可以把左边整理成乘积导数。",
    "goal":"认出线性方程的系数并计算积分因子，为后续整体求导做准备。",
    "pause_seconds":2.6,"write_seconds":1.05,
    "math":[
      {"id":"factor",
       "latex":r"\mu(x)=e^{\int 2x\,\mathrm{d}x}=e^{x^2}",
       "reason":"将未知函数前的系数积分并取指数，得到正确的积分因子。"},
    ],
  },
  {
    "id":"derive","event_type":"derivation","phase":"knowledge",
    "heading":"为什么左边能合并",
    "detail":"乘上积分因子后，对照乘积求导公式，再对两边积分。",
    "goal":"完整展示乘积分解与积分过程，不能跳过等式变形。",
    "pause_seconds":3.0,"write_seconds":1.0,
    "math":[
      {"id":"multiply",
       "latex":r"e^{x^2}y'+2xe^{x^2}y=2xe^{x^2}",
       "reason":"方程两侧同乘非零积分因子。"},
      {"id":"product_rule",
       "latex":r"(ye^{x^2})'=e^{x^2}y'+2xe^{x^2}y",
       "reason":"由乘积求导和链式法则验证左侧为何可以合并。"},
      {"id":"combined",
       "latex":r"(ye^{x^2})'=2xe^{x^2}",
       "reason":"将左侧合并为一个乘积的导数。"},
      {"id":"integrated",
       "latex":r"ye^{x^2}=\int 2xe^{x^2}\,\mathrm{d}x=e^{x^2}+C",
       "reason":"对两边积分并保留任意常数。"},
    ],
  },
  {
    "id":"initial","event_type":"application","phase":"application",
    "heading":"再代入初始条件",
    "detail":"先把未知函数单独写出来，再用给定初值确定常数。",
    "goal":"求一般解并通过给定初值确定唯一特解。",
    "pause_seconds":2.4,"write_seconds":1.05,
    "math":[
      {"id":"general",
       "latex":r"y=1+Ce^{-x^2}",
       "reason":"两侧除以正的指数因子，写出一般解。"},
      {"id":"constant",
       "latex":r"0=y(0)=1+C,\;C=-1",
       "reason":"直接利用零点处初值确定积分常数，避免拆成无意义两幕。"},
      {"id":"solution",
       "latex":r"y=1-e^{-x^2}",
       "reason":"代回积分常数，得到所求初值问题解。"},
    ],
  },
  {
    "id":"verify","event_type":"summary","phase":"pitfall",
    "heading":"核对求导的符号",
    "detail":"负指数的求导还要乘内层导数，两个负号抵消，再检验方程与初值。",
    "goal":"完整检验微分方程与初值，指出最可能出现的负号错误。",
    "pause_seconds":3.0,"write_seconds":1.0,
    "math":[
      {"id":"derivative",
       "latex":r"y'=2xe^{-x^2}",
       "reason":"使用链式法则，并核对两次负号抵消。"},
      {"id":"odecheck",
       "latex":r"y'+2xy=2xe^{-x^2}+2x(1-e^{-x^2})=2x",
       "reason":"代回原微分方程左侧，确实等于右侧。"},
      {"id":"initialcheck",
       "latex":r"y(0)=1-e^0=0",
       "reason":"复核给定的初始条件，保证得到的是该初值问题的解。"},
    ],
  },
]


def build_new():
    package,board,execution,cues=compile_teaching_units(
        problem=PROBLEM,reference_solution=REFERENCE_SOLUTION,units=UNITS
    )
    policy=simple_classroom_policy(result_ids=("m_solution",))
    return package,board,execution,cues,policy


def main(output:Path):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    package,board,execution,cues,policy=build_new()
    files={
      "new_ode_problem_and_solution.json":{
        "problem":PROBLEM,"reference_solution":REFERENCE_SOLUTION,
        "expected_solution":r"y=1-e^{-x^2}",
        "topic":"first-order-linear-ODE-IVP",
        "unit_count":len(UNITS),
        "formula_write_count":sum(len(u["math"]) for u in UNITS),
      },
      "teaching_units.json":{"schema_version":"1.0","units":UNITS},
      "teaching_package.json":package,
      "storyboard.json":board.model_dump(mode="json"),
      "execution.json":execution.model_dump(mode="json"),
      "teacher_approved_cues.json":cues,
      "page_policy.json":policy,
    }
    for path,data in files.items():
        (output/path).write_text(
            json.dumps(data,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8"
        )
    print("NEW_ODE_PEDAGOGICAL_UNITS",len(UNITS),
          "ACTUAL_MATH_WRITES",sum(len(u["math"]) for u in UNITS))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    main(p.parse_args().output)
