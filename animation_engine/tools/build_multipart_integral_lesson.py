"""V2.5.1 new, teacher-reviewed calculation lessons.

A: three different integrals (integration by parts, substitution, power).
B: a longer double integration-by-parts item with an explicitly safe
   intermediate checkpoint, supporting continuation on a new blackboard.
C: five terms stress-test dynamic result ledger, not hardcoded to three.
No AI, TTS or synthetic speech alignment; actual verification is independent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy


def math(id: str, tex: str, why: str) -> dict:
    return {"id":id,"latex":tex,"reason":why}


def unit(id: str, heading: str, detail: str, goal: str, writes: list,
         phase: str="calculate",type: str="derivation") -> dict:
    return {
        "id":id,"event_type":type,"phase":phase,
        "heading":heading,"detail":detail,"goal":goal,
        "pause_seconds":2.0 if phase=="calculate" else 2.4,
        "write_seconds":.85,
        "math":writes,
    }


I1=[
    math("i1_knowledge",
         r"\int_a^b u\,\mathrm{d}v=[uv]_a^b-\int_a^b v\,\mathrm{d}u",
         "分部积分的通用公式，先讲清变量和边界项。"),
    math("i1_choice",r"u=x,\; \mathrm{d}v=e^x\,\mathrm{d}x",
         "把代数因子选为求导对象，指数因子用于积分。"),
    math("i1_definition",r"I_1=\int_0^1xe^x\,\mathrm{d}x",
         "定义第一部分，选择分部积分。"),
    math("i1_parts",r"I_1=[xe^x]_0^1-\int_0^1e^x\,\mathrm{d}x",
         "分部积分，边界项与剩余积分均必须展示。"),
    math("i1_eval",r"I_1=e-(e-1)",
         "正确计算原始端点与指数函数端点。"),
    math("i1_result",r"I_1=1",
         "整理并保留第一项的计算结果。"),
]
I2=[
    math("i2_knowledge",
         r"\int f(g(x))g'(x)\,\mathrm{d}x=\int f(u)\,\mathrm{d}u",
         "换元积分公式；定积分还必须更换上下限。"),
    math("i2_definition",r"I_2=\int_0^1\frac{x}{1+x^2}\,\mathrm{d}x",
         "定义第二项，分母的导数与分子匹配。"),
    math("i2_substitution",r"u=1+x^2,\;\mathrm{d}u=2x\,\mathrm{d}x",
         "明确变量替换和微分关系，而不是直接跳到对数。"),
    math("i2_bounds",r"I_2=\frac12\int_1^2\frac1u\,\mathrm{d}u",
         "把积分限一同换成新变量的上下限。"),
    math("i2_result",r"I_2=\frac12[\ln u]_1^2=\frac12\ln2",
         "代入新积分限，得到第二项结果。"),
]
I3=[
    math("i3_knowledge",
         r"\int x^n\,\mathrm{d}x=\frac{x^{n+1}}{n+1}+C,\ n\ne-1",
         "幂函数积分，指数加一再除以新指数。"),
    math("i3_result",r"I_3=\int_0^1x^2\,\mathrm{d}x=\frac13",
         "基础幂函数积分直接连写，不强制拆成知识点。"),
]
I4=[
    math("i4_knowledge",
         r"\int\sin x\,\mathrm{d}x=-\cos x+C",
         "正弦积分的原函数，定积分再计算端点差。"),
    math("i4_result",
         r"I_4=\int_0^1\sin x\,\mathrm{d}x=1-\cos1",
         "已知正弦的原函数，直接计算定积分。"),
]
I5=[
    math("i5_knowledge",
         r"\int e^x\,\mathrm{d}x=e^x+C",
         "指数函数积分的原函数。"),
    math("i5_result",
         r"I_5=\int_0^1e^x\,\mathrm{d}x=e-1",
         "基础指数函数积分一次完成。"),
]


def _common(variant: str):
    if variant not in ("A","B","C"):
        raise ValueError("V2.5.1 variant must be A, B or C")
    if variant=="A":
        problem=(
            r"求定积分：\int_0^1\left(xe^x+\frac{x}{1+x^2}+x^2\right)\,\mathrm{d}x."
        )
        part_formulas=[I1,I2,I3]
        final=[
            math("final",
                 r"I=1+\frac12\ln2+\frac13=\frac43+\frac12\ln2",
                 "全部分项算完后才合并积分结果。")
        ]
        result_tex=r"\frac43+\frac12\ln2"
    elif variant=="B":
        problem=(
            r"求定积分：\int_0^1\left(x+x^2e^x+\sin x\right)\,\mathrm{d}x."
        )
        part_formulas=[
            [
                math("b_i1_power",
                     r"\int x^n\,\mathrm{d}x=\frac{x^{n+1}}{n+1}+C,\ n\ne-1",
                     "先列出基本幂函数积分公式。"),
                math("i1_result",r"I_1=\int_0^1x\,\mathrm{d}x=\frac12",
                     "直接计算简单的第一项，不机械多拆。"),
            ],
            [
                math("b_i2_parts",
                     r"\int_a^b u\,\mathrm{d}v=[uv]_a^b-\int_a^b v\,\mathrm{d}u",
                     "再次应用分部积分法，先明确它的通用公式。"),
                math("b_i2_choice",r"u=x^2,\; \mathrm{d}v=e^x\,\mathrm{d}x",
                     "让二次幂求导，从而逐步降低幂次。"),
                math("i2_definition",r"I_2=\int_0^1x^2e^x\,\mathrm{d}x",
                     "这一项需要连续两次分部积分。"),
                math("i2_first_parts",
                     r"I_2=[x^2e^x]_0^1-2\int_0^1xe^x\,\mathrm{d}x",
                     "展示第一次分部积分的完整边界项。"),
                math("i2_checkpoint",
                     r"I_2=e-2J,\;J=\int_0^1xe^x\,\mathrm{d}x",
                     "经过第一次分部积分得到第二次计算所需的可靠关系。"),
            ],
            [
                math("b_i2_j_rule",
                     r"\int_a^b u\,\mathrm{d}v=[uv]_a^b-\int_a^b v\,\mathrm{d}u",
                     "第二次分部积分前，重新给出所用公式。"),
                math("b_i2_j_choice",
                     r"u=x,\; \mathrm{d}v=e^x\,\mathrm{d}x",
                     "计算子积分时再次应用前面讲过的分部积分公式。"),
                math("i2_j_parts",
                     r"J=[xe^x]_0^1-\int_0^1e^x\,\mathrm{d}x",
                     "再次分部积分求出子积分 J。"),
                math("i2_j_result",
                     r"J=e-(e-1)=1",
                     "代入上下限，得到 J 的准确值。"),
                math("i2_result",
                     r"I_2=e-2",
                     "代回第一步保留的关系，完成这一项。"),
            ],
            [
                math("b_i3_sine",r"\int\sin x\,\mathrm{d}x=-\cos x+C",
                     "先写正弦函数积分公式，再代入端点。"),
                math("i3_result",
                     r"I_3=\int_0^1\sin x\,\mathrm{d}x=1-\cos1",
                     "直接求第三项的定积分。"),
            ],
        ]
        final=[
            math("final",
                 r"I=\frac12+(e-2)+(1-\cos1)=e-\frac12-\cos1",
                 "完整计算三个分项以后才做总合并。")
        ]
        result_tex=r"e-\frac12-\cos1"
    else:
        problem=(
            r"求定积分：\int_0^1\left(xe^x+\frac{x}{1+x^2}+x^2+\sin x+e^x\right)\,\mathrm{d}x."
        )
        part_formulas=[I1,I2,I3,I4,I5]
        final=[
            math("final",
                 r"I=e+\frac43+\frac12\ln2-\cos1",
                 "最后合并常数，不遗漏任何一项。"),
        ]
        result_tex=r"e+\frac43+\frac12\ln2-\cos1"
    return problem,part_formulas,final,result_tex


def build_variant(variant: str):
    problem,segments,final,result_tex=_common(variant)
    count=3 if variant in ("A","B") else 5
    relation="I="+ "+".join("I_"+str(i) for i in range(1,count+1))
    units=[
        unit(
            "split","根据线性性质拆项","先把各部分记下来，然后按顺序计算，最后统一合并。",
            "解释定积分的线性性质并建立各项之间的总关系。",
            [math("decomposition",relation,
                  "建立各个子积分与原积分的准确关系。")],
            phase="strategy",type="orient"
        )
    ]
    groups=[]
    if variant=="B":
        units.append(unit(
            "i1","幂函数积分公式","这一项是普通的幂函数积分，直接写出结果。",
            "完成第一项，无需冗余拆步。",segments[0],phase="knowledge"
        ))
        groups.append({
            "id":"I1","event_ids":["e_i1"],"result_object_id":"m_i1_result",
            "knowledge_object_id":"m_b_i1_power",
            "safe_break_after":[],"checkpoints":[]
        })
        units.append(unit(
            "i2start","分部积分公式与本题取值",
            "先把二次幂降低为一次幂，保留需要继续计算的中间积分。",
            "第一段求出第二次分部积分所依赖的准确中间关系。",
            segments[1],phase="knowledge"
        ))
        units.append(unit(
            "i2finish","分部积分法求子积分",
            "再次使用分部积分公式求子积分，算完后代回原式。",
            "沿用前面已经得到的中间关系，完成第二项。",
            segments[2],phase="knowledge"
        ))
        groups.append({
            "id":"I2","event_ids":["e_i2start","e_i2finish"],
            "result_object_id":"m_i2_result",
            "knowledge_object_id":"m_b_i2_parts",
            "safe_break_after":["e_i2start"],
            "checkpoints":[{"event_id":"e_i2start",
                            "object_id":"m_i2_checkpoint"}]
        })
        units.append(unit(
            "i3","正弦函数积分公式","这一项可直接利用正弦函数的原函数。",
            "完成第三项。",segments[3],phase="knowledge"
        ))
        groups.append({
            "id":"I3","event_ids":["e_i3"],"result_object_id":"m_i3_result",
            "knowledge_object_id":"m_b_i3_sine",
            "safe_break_after":[],"checkpoints":[]
        })
    else:
        for i,items in enumerate(segments,1):
            part="I"+str(i)
            uid="i"+str(i)
            phase="knowledge"
            heading=(
                "分部积分法" if i==1
                else "换元积分法" if i==2
                else "幂函数积分" if i==3
                else "正弦函数积分" if i==4 else "指数函数积分"
            )
            detail=(
                "使用分部积分公式，先选变量，再算边界项。" if i==1
                else "使用换元积分公式，并同步更换上下限。" if i==2
                else "先根据积分公式，再直接计算本题上下限。"
            )
            units.append(unit(
                uid,heading,detail,"完整计算并保留第"+str(i)+"项的准确结果。",
                items,phase=phase
            ))
            groups.append({
                "id":part,"event_ids":["e_"+uid],
                "result_object_id":"m_"+items[-1]["id"],
                "knowledge_object_id":"m_"+items[0]["id"],
                "safe_break_after":[],"checkpoints":[]
            })
    if variant=="C":
        units.append(unit(
            "recap","把五项结果汇到同一行",
            "五个结果都已经算完，先按原式列出再进行最后合并。",
            "在长题换板时用已审核的完整五项结果承接后续计算。",
            [math("recap",
                  r"I=1+\frac12\ln2+\frac13+(1-\cos1)+(e-1)",
                  "只引用已经全部算出的五项真实结果。")],
            phase="application",type="application"
        ))
    units.append(unit(
        "final","把已得的各项结果汇总",
        "前面的每个积分都有了结果，现在统一代入总关系计算。",
        "在每个分项完成之后合并，并保持结果来源可追溯。",
        final,phase="summary",type="conclusion"
    ))
    ref="\n".join(
        ["题目中积分按线性性质拆成"+str(count)+"项。"]
        + [w["latex"] for u in units for w in u["math"]]
        + ["所有步骤均已由教师逐式审核。"]
    )
    package,board,execution,cues=compile_teaching_units(
        problem=problem,reference_solution=ref,units=units,
        teacher_reviewed=True
    )
    groups_manifest={
        "schema_version":"1.0",
        "mode":"multi_part_computation",
        "teacher_reviewed":True,
        "source_storyboard_sha256":execution.source_storyboard_sha256,
        "decomposition":{
            "event_id":"e_split","object_id":"m_decomposition"
        },
        "parts":groups,
        "final":{"event_id":"e_final","object_id":"m_final"},
    }
    if variant=="C":
        groups_manifest["recap"]={
            "event_id":"e_recap","object_id":"m_recap"
        }
    # Computation carry is determined by the verified result ledger, not a
    # fixed handpicked set from the previous demo's single equation.
    policy=simple_classroom_policy()
    return package,board,execution,cues,policy,groups_manifest,units,problem,result_tex


def export_variant(output: Path,variant: str):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    package,board,execution,cues,policy,groups,units,problem,result=build_variant(variant)
    records={
        "problem.json":{
            "variant":variant,"original_problem":problem,
            "expected_result":result,"independent_check":"CI sympy integral",
            "parts_count":len(groups["parts"]),
            "units_count":len(units),
        },
        "teaching_units.json":{"schema_version":"1.0","units":units},
        "teaching_package.json":package,
        "storyboard.json":board.model_dump(mode="json"),
        "execution.json":execution.model_dump(mode="json"),
        "teacher_approved_cues.json":cues,
        "page_policy.json":policy,
        "computation_groups.json":groups,
    }
    for name,data in records.items():
        (output/name).write_text(
            json.dumps(data,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8"
        )
    print("V2_5_1_NEW_MULTIPART",variant,
          len(groups["parts"]),"parts",len(units),"teaching units")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--variant",choices=("A","B","C"),default="A")
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    export_variant(args.output,args.variant)
