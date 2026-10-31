"""V2.5.3 teacher-reviewed proofs: induction, inequality, parameter cases.

The content author provides exact math and dependency references. The engine
may only render, retain or reject those approved sources, never infer proof
steps or collapse a mathematical subgoal into meaningless tiny writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy


def math(name: str, latex: str, reason: str) -> dict:
    return {"id":name,"latex":latex,"reason":reason}


def unit(name, title, detail, goal, writes, *, phase="calculate", event_type="proof"):
    return {
        "id":name,"heading":title,"detail":detail,"goal":goal,
        "phase":phase,"event_type":event_type,"math":writes,
        "pause_seconds":2.0 if phase=="calculate" else 2.3,
        "write_seconds":0.82,
    }


def stage(uid: str, role: str, outputs: list[str], citations: list[str],
          *, case_group=None, case_id=None, safe=True) -> dict:
    def ref(x):
        return "m_"+x
    carry=list(dict.fromkeys(["condition","goal"]+citations)) if role!="setup" else []
    return {
        "event_id":"e_"+uid, "role":role,
        "output_ids":[ref(x) for x in outputs],
        "cites":[ref(x) for x in citations],
        "carry_ids":[ref(x) for x in carry],
        "safe_break_after":safe,
        "case_group":case_group,"case_id":case_id,
    }


def induction():
    problem=(r"证明立方和公式：\sum_{k=1}^{n}k^3="
             r"\left(\frac{n(n+1)}{2}\right)^2.")
    units=[
        unit("setup","确定归纳目标","先明确正整数范围与要证明的恒等式。",
             "写清归纳对象和待证命题，不能把目标当作已证结论。",
             [math("condition",r"n\in\mathbb{N},\quad n\geq1","正整数范围。"),
              math("definition",r"S_n=\sum_{k=1}^{n}k^3","为立方和作标准记号。"),
              math("goal",r"S_n=\left(\frac{n(n+1)}{2}\right)^2",
                   "这是待证恒等式，不是已证结果。")],phase="strategy",event_type="orient"),
        unit("knowledge_induction","数学归纳法原理",
             "从首项成立和归纳递推两点建立对所有正整数成立的结论。",
             "学习数学归纳法的通用原理，再将原理用于本题。",
             [math("principle_premises",r"P(1),\quad P(k)\Longrightarrow P(k+1)",
                   "数学归纳法要求起点成立并证明递推成立。"),
              math("principle_conclusion",r"\Longrightarrow P(n),\quad \forall n\geq1",
                   "归纳法原理给出适用于所有正整数的结论。")],
             phase="knowledge",event_type="orient"),
        unit("base","检验归纳起点","把初始整数代入两边，验证首项成立。",
             "完成数学归纳法的起始条件。",
             [math("base_left",r"S_1=1^3=1","计算求和的第一项。"),
              math("base_result",r"\left(\frac{1(1+1)}2\right)^2=1",
                   "归纳目标右侧在首项处也为一。")],phase="calculate"),
        unit("hypothesis","写出归纳假设","假定某个正整数处结论成立，然后证明下一项。",
             "清楚区分归纳假设与已经证明的初始情形。",
             [math("hypothesis",r"S_n=\frac{n^2(n+1)^2}{4}",
                   "明确写出只用于归纳步骤的假设。")],phase="calculate"),
        unit("successor","从下一项的和出发","把末项单独提出，再代入归纳假设。",
             "由已知前项之和推导下一个整数的公式。",
             [math("successor_split",r"S_{n+1}=S_n+(n+1)^3",
                   "立方和的定义使下一项只增加一个立方。"),
              math("successor_subst",
                   r"S_{n+1}=\frac{n^2(n+1)^2}{4}+(n+1)^3",
                   "代入而非凭空写出下一项的公式。")]),
        unit("factor","提取公共平方因子","把共同的平方因子提取出来，便于化简。",
             "让下一项计算与归纳目标建立准确关系。",
             [math("factor_result",
                   r"S_{n+1}=(n+1)^2\left(\frac{n^2}{4}+n+1\right)",
                   "从上一式提取共同因子，保持每一项正确。")]),
        unit("lemma","计算括号内的表达式","把括号中的三项通分合并，识别完全平方。",
             "证明归纳计算需要的代数恒等式。",
             [math("lemma_result",
                   r"\frac{n^2}{4}+n+1=\frac{(n+2)^2}{4}",
                   "通分后分子为 n 平方加四 n 加四。")],
             phase="calculate"),
        unit("successor_done","得到下一整数的结论","代回完全平方，得到下一项与目标同形。",
             "验证归纳步骤从成立推进到下一整数。",
             [math("successor_result",
                   r"S_{n+1}=\left(\frac{(n+1)(n+2)}2\right)^2",
                   "代入引理，完成 n 到 n 加一的数学推导。")]),
        unit("final","完成归纳证明","起点成立且归纳步骤成立，所以公式成立。",
             "总结归纳基础和归纳递推的有效性。",
             [math("final",
                   r"\sum_{k=1}^{n}k^3=\left(\frac{n(n+1)}2\right)^2",
                   "对每个正整数得到原命题。")],
             phase="summary",event_type="conclusion"),
    ]
    stages=[
        stage("setup","setup",["condition","definition","goal"],[]),
        stage("knowledge_induction","lemma",
              ["principle_premises","principle_conclusion"],["condition","goal"]),
        stage("base","derivation",["base_left","base_result"],
              ["condition","goal","principle_premises"]),
        stage("hypothesis","derivation",["hypothesis"],["goal","principle_premises"]),
        stage("successor","derivation",["successor_split","successor_subst"],
              ["definition","hypothesis"]),
        stage("factor","derivation",["factor_result"],["successor_subst"]),
        stage("lemma","lemma",["lemma_result"],["factor_result"]),
        stage("successor_done","derivation",["successor_result"],
              ["lemma_result","principle_conclusion"]),
        stage("final","conclusion",["final"],
              ["goal","base_result","successor_result"],safe=False),
    ]
    return problem,units,stages,[]


def inequality():
    problem=(r"证明并讨论等号：\left(x+y+z\right)^2"
             r"\leq3\left(x^2+y^2+z^2\right).")
    units=[
        unit("setup","确定不等式与等号","先写实数条件，再比较左右两边。",
             "写下条件及欲证明的不等式。",
             [math("condition",r"x,y,z\in\mathbb{R}","三个变量均为实数。"),
              math("goal",r"(x+y+z)^2\leq3(x^2+y^2+z^2)",
                   "这是当前要求证明的不等式。")],
             phase="strategy",event_type="orient"),
        unit("difference","构造两边的差","证明右边减左边非负，就能得到原结论。",
             "把不等式转化为差值非负问题。",
             [math("difference",
                   r"D=3(x^2+y^2+z^2)-(x+y+z)^2",
                   "构造右边减左边的表达式。")],phase="knowledge"),
        unit("expand","准确展开平方项","按平方公式逐项展开并合并同类项。",
             "对差值进行正确的二次式计算。",
             [math("expand",
                   r"D=2(x^2+y^2+z^2-xy-xz-yz)",
                   "平方展开后，交叉项系数为负二。")]),
        unit("squares","转换为三个平方和","将整理后的差值改写成三项平方。",
             "构造非负性的直接依据，而不跳过关键恒等式。",
             [math("squares",
                   r"D=(x-y)^2+(y-z)^2+(z-x)^2",
                   "展开右侧可以恢复完全相同的差值。")],
             phase="knowledge"),
        unit("nonnegative","根据平方的非负性","每个实数平方都非负，所以三项之和非负。",
             "从恒等式推出目标不等式。",
             [math("nonnegative",r"D\geq0",
                   "三个实数平方的和必定不小于零。"),
              math("result",r"(x+y+z)^2\leq3(x^2+y^2+z^2)",
                   "差值非负意味着原不等式成立。")]),
        unit("equality","分析等号成立条件","三个平方同时为零，三个变量才全部相等。",
             "给出等号成立的充分必要条件。",
             [math("eq_condition",r"x-y=0,\quad y-z=0,\quad z-x=0",
                   "平方和等于零的必要条件。"),
              math("eq_result",r"x=y=z",
                   "三个差均为零当且仅当三个变量相等。")],
             phase="check"),
        unit("final","归纳证明与等号条件","不等式对全体实数成立，等号条件也已确定。",
             "综合非负性和等号条件。",
             [math("final",r"D\geq0,\quad D=0\;\Longleftrightarrow\;x=y=z",
                   "结论同时记录非负性和等号的全部条件。")],
             phase="summary",event_type="conclusion"),
    ]
    stages=[
        stage("setup","setup",["condition","goal"],[]),
        stage("difference","derivation",["difference"],["condition","goal"]),
        stage("expand","derivation",["expand"],["difference"]),
        stage("squares","lemma",["squares"],["expand"]),
        stage("nonnegative","derivation",["nonnegative","result"],
              ["squares","goal"]),
        stage("equality","derivation",["eq_condition","eq_result"],
              ["squares","nonnegative"]),
        stage("final","conclusion",["final"],["result","eq_result"],safe=False),
    ]
    return problem,units,stages,[]


def parameter_cases():
    problem=r"求参数范围：\forall x\in\mathbb{R},\;x^2-2ax+1\geq0."
    units=[
        unit("setup","明确全体实数条件","题目要求所有实数处都非负，先明确参数是实数。",
             "记下参数范围与完整的待证目标。",
             [math("condition",r"a\in\mathbb{R}","参数是实数。"),
              math("goal",r"\forall x\in\mathbb{R},\quad x^2-2ax+1\geq0",
                   "这里的全称量词不能丢掉。")],
             phase="strategy",event_type="orient"),
        unit("square","先对二次式配方","直接配成一个平方加常数，便于讨论参数。",
             "建立不漏掉任意实数的推导基础。",
             [math("square",r"x^2-2ax+1=(x-a)^2+1-a^2",
                   "等式对所有实数参数和变量均成立。")],
             phase="knowledge"),
        unit("necessary","检查最关键的取值","令变量等于参数，立刻得到非负性的必要条件。",
             "先给出参数范围的必要性，而非先猜答案。",
             [math("critical",r"x=a,\quad x^2-2ax+1=1-a^2",
                   "选取配方后平方为零的位置。")]),
        unit("case_less","第一类参数情形","常数项严格为正，任意平方加它仍为正。",
             "讨论参数平方小于一时原条件充分成立。",
             [math("less_assume",r"a^2<1,\quad1-a^2>0",
                   "这是此类情况的参数假设。"),
              math("less_result",r"(x-a)^2+1-a^2>0",
                   "任意实数 x 处二次式都严格为正。")],
             phase="strategy"),
        unit("case_equal","第二类参数情形","常数项等于零时，原式成为一个完全平方。",
             "讨论参数平方恰好等于一的边界情况。",
             [math("equal_assume",r"a^2=1,\quad1-a^2=0",
                   "这是边界参数的假设。"),
              math("equal_result",r"(x-a)^2+1-a^2=(x-a)^2\geq0",
                   "任意实数 x 处仍然非负。")],
             phase="strategy"),
        unit("case_greater","第三类参数情形","若常数项为负，取变量等于参数便能否定原条件。",
             "证明参数平方大于一的情形不满足全称要求。",
             [math("greater_assume",r"a^2>1,\quad1-a^2<0",
                   "此处参数平方大于一。"),
              math("greater_result",r"x=a,\quad x^2-2ax+1<0",
                   "找到一个反例就能否定对所有实数成立。")],
             phase="strategy"),
        unit("merge","把三种情形合并","前两类满足要求，第三类不能满足要求。",
             "汇总已经完整讨论的三个参数情形。",
             [math("merge",r"a^2\leq1",
                   "参数平方不大于一是充分必要的限制。")],
             phase="check"),
        unit("final","写出最终参数区间","将参数平方的约束转成标准区间形式。",
             "完整给出参数分类讨论后的总结果。",
             [math("final",r"-1\leq a\leq1",
                   "包含两端点，范围没有遗漏。")],
             phase="summary",event_type="conclusion"),
    ]
    stages=[
        stage("setup","setup",["condition","goal"],[]),
        stage("square","derivation",["square"],["condition","goal"]),
        stage("necessary","lemma",["critical"],["square","goal"]),
        stage("case_less","case",["less_assume","less_result"],
              ["condition","square"],case_group="parameter_sign",case_id="less"),
        stage("case_equal","case",["equal_assume","equal_result"],
              ["condition","square"],case_group="parameter_sign",case_id="equal"),
        stage("case_greater","case",["greater_assume","greater_result"],
              ["condition","critical"],case_group="parameter_sign",case_id="greater"),
        stage("merge","merge",["merge"],
              ["less_result","equal_result","greater_result"]),
        stage("final","conclusion",["final"],["goal","merge"],safe=False),
    ]
    groups=[{
        "group_id":"parameter_sign",
        "cases":["less","equal","greater"],
        "merge_event_id":"e_merge",
    }]
    return problem,units,stages,groups


_BUILD={"A":induction,"B":inequality,"C":parameter_cases}


def build_variant(variant: str):
    if variant not in _BUILD:
        raise ValueError("PROOF_UNKNOWN_VARIANT")
    problem,units,stages,groups=_BUILD[variant]()
    reference="\n".join(
        [problem]+[step["latex"] for u in units for step in u["math"]]
    )
    package,board,execution,cues=compile_teaching_units(
        problem=problem,reference_solution=reference,
        units=units,teacher_reviewed=True
    )
    manifest={
        "schema_version":"1.0",
        "mode":"verified_proof_chain",
        "teacher_reviewed":True,
        "source_storyboard_sha256":execution.source_storyboard_sha256,
        "anchors":{"condition_object_id":"m_condition",
                   "goal_object_id":"m_goal"},
        "stages":stages,
        "branch_groups":groups,
    }
    policy=simple_classroom_policy()
    return package,board,execution,cues,policy,manifest,units


def export_variant(output: Path,variant: str):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    package,board,execution,cues,policy,manifest,units=build_variant(variant)
    files={
        "problem.json":{"variant":variant,"kind":{
            "A":"induction","B":"inequality","C":"parameter_cases"}[variant],
            "teacher_reviewed":True},
        "teaching_units.json":{"schema_version":"1.0","units":units},
        "teaching_package.json":package,
        "storyboard.json":board.model_dump(mode="json"),
        "execution.json":execution.model_dump(mode="json"),
        "teacher_approved_cues.json":cues,
        "page_policy.json":policy,
        "proof_chain.json":manifest,
    }
    for filename,data in files.items():
        (output/filename).write_text(
            json.dumps(data,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8"
        )
    print("V2_5_3_PROOF_LESSON",variant,len(manifest["stages"]),
          "stages",len(manifest["branch_groups"]),"branch groups")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--variant",choices=sorted(_BUILD),required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    export_variant(args.output,args.variant)
