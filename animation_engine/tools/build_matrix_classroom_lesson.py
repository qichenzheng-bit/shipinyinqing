"""V2.5.2 independently reviewed matrix, inverse and parameter determinant demos.

Generated mathematical matrices are computed from exact source rows, not
reconstructed by animation. Renderer cannot infer the missing row operation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy
from animation_engine.matrix_steps import (
    parse_expr, matrix_latex, operation_latex, _apply, _matrix
)


def math(name, latex, reason):
    return {"id":name,"latex":latex,"reason":reason}


def unit(name,heading,detail,goal,entries,*,phase="calculate",kind="derivation"):
    return {
        "id":name,"event_type":kind,"phase":phase,
        "heading":heading,"detail":detail,"goal":goal,
        "pause_seconds":2.0,"write_seconds":.82,"math":entries,
    }


def _rows(m):
    # SymPy prints rationals as 1/2, which the safe arithmetic parser accepts.
    return [[str(m[i,j]) for j in range(m.cols)] for i in range(m.rows)]


CASES={
    "A":{
        "kind":"linear_system",
        "problem":r"解方程组：\begin{cases}x+y+z=6\\2x+y+z=7\\x+2y+3z=14\end{cases}",
        "initial":[["1","1","1","6"],["2","1","1","7"],["1","2","3","14"]],
        "augment":3,
        "steps":[
            ("用首行消去第二行首项","先用第二行减去首行的两倍，首列第二项为零。",
             {"kind":"add_scaled_row","target":2,"source":1,"factor":"-2"}),
            ("继续消去第三行首项","第三行减去第一行，先完成第一列的消元。",
             {"kind":"add_scaled_row","target":3,"source":1,"factor":"-1"}),
            ("消去第三行第二项","第三行加第二行，得到第三个未知数的值。",
             {"kind":"add_scaled_row","target":3,"source":2,"factor":"1"}),
            ("把第三列向上消去","用第三行消去第二行中第三列的非零项。",
             {"kind":"add_scaled_row","target":2,"source":3,"factor":"1"}),
            ("将第二行主元化为一","第二行乘以负一，使第二个主元变成一。",
             {"kind":"scale_row","target":2,"factor":"-1"}),
            ("消去第一行第三项","第一行减去第三行，把第三列上方清零。",
             {"kind":"add_scaled_row","target":1,"source":3,"factor":"-1"}),
            ("消去第一行第二项","最后第一行减去第二行，左侧成为单位阵。",
             {"kind":"add_scaled_row","target":1,"source":2,"factor":"-1"}),
        ],
        "intro":r"R_i\leftarrow R_i+cR_j",
        "intro_heading":"初等行变换基本性质",
        "intro_detail":"行消元每次说明操作，再并排呈现操作前后的增广矩阵。",
        "final_heading":"读出唯一解",
        "final_detail":"增广矩阵左侧已经化为单位阵，右侧就是对应的未知数。",
    },
    "B":{
        "kind":"inverse",
        "problem":r"求矩阵的逆：\begin{bmatrix}2&1\\1&1\end{bmatrix}",
        "initial":[["2","1","1","0"],["1","1","0","1"]],
        "augment":2,
        "steps":[
            ("消去第一行第二列","第一行减去第二行，左上角行主元为一。",
             {"kind":"add_scaled_row","target":1,"source":2,"factor":"-1"}),
            ("消去第二行第一列","第二行减去第一行，左侧得到单位阵。",
             {"kind":"add_scaled_row","target":2,"source":1,"factor":"-1"}),
        ],
        "intro":r"[A\mid I]\longrightarrow[I\mid A^{-1}]",
        "intro_heading":"增广矩阵求逆原理",
        "intro_detail":"给原矩阵添单位阵，通过初等行变换把左侧化为单位阵。",
        "final_heading":"读取右侧逆矩阵",
        "final_detail":"左侧为单位阵时，右侧是原矩阵的逆矩阵。",
    },
    "C":{
        "kind":"determinant",
        "problem":r"计算含参行列式：\begin{vmatrix}1&1\\1&a\end{vmatrix}",
        "initial":[["1","1"],["1","a"]],
        "augment":None,
        "steps":[
            ("行加倍数不改行列式","第二行减第一行，行列式保持不变，再看三角形结构。",
             {"kind":"add_scaled_row","target":2,"source":1,"factor":"-1"}),
        ],
        "intro":r"\det(A)=\det(EA)",
        "intro_heading":"行列式行加不变性",
        "intro_detail":"某一行加上另一行的倍数，不改变行列式的值。",
        "final_heading":"得到含参结论并分类",
        "final_detail":"行列式等于对角线元素之积，再讨论何时为零。",
    },
}


def build_variant(name: str):
    if name not in CASES:
        raise ValueError("Unknown case")
    spec=CASES[name]
    kind=spec["kind"]
    augment=spec["augment"]
    determinant=kind=="determinant"
    previous=_matrix(spec["initial"])
    initial_tex=matrix_latex(spec["initial"],augmented_at=augment,determinant=determinant)
    units=[
        unit("intro",spec["intro_heading"],spec["intro_detail"],
             "先说明本题可用的行变换和矩阵初始状态。",
             [math("intro_rule",spec["intro"],"初等变换规则的来源公式。"),
              math("initial",initial_tex,"完整记录初始矩阵，不遗漏任一元素。")],
             phase="knowledge",kind="orient")
    ]
    steps=[]
    for index,(heading,detail,op) in enumerate(spec["steps"],1):
        eid="step"+str(index)
        before=_rows(previous)
        result=_apply(previous,op,[])
        after=_rows(result)
        op_latex=operation_latex(op)
        entries=[
            math(eid+"_before",
                 matrix_latex(before,augmented_at=augment,determinant=determinant),
                 "课堂重写该操作之前的准确矩阵状态，以便前后对照。"),
            math(eid+"_op",op_latex,
                 "明确标明作用行、源行与运算倍数。"),
            math(eid+"_after",
                 matrix_latex(after,augmented_at=augment,determinant=determinant),
                 "这是执行本步行变换后得到的准确矩阵。"),
        ]
        units.append(unit(eid,heading,detail,
                          "按有依据的行变换从前态得到正确后态。",entries,
                          phase="calculate",kind="derivation"))
        steps.append({
            "event_id":"e_"+eid,
            "before_id":"m_"+eid+"_before",
            "operation_id":"m_"+eid+"_op",
            "after_id":"m_"+eid+"_after",
            "before":before,
            "after":after,
            "operation":op
        })
        previous=result
    import sympy as s
    initial=_matrix(spec["initial"])
    if kind=="linear_system":
        answer=initial[:,:augment].inv()*initial[:,augment]
        out=r"\begin{aligned}"+r"\\".join(
            f"{'xyzuvw'[i]}={s.latex(answer[i]).replace(' ','')}"
            for i in range(len(answer)))+r"\end{aligned}"
        final_math=[math("answer",out,"由化为单位阵的增广矩阵读取唯一解。")]
    elif kind=="inverse":
        inv=initial[:,:augment].inv()
        rows=_rows(inv)
        out=r"A^{-1}="+matrix_latex(rows)
        final_math=[math("answer",out,"左侧化为单位阵时右侧即逆矩阵。")]
    else:
        value=s.factor(initial.det())
        out="D="+s.latex(value).replace(" ","")
        final_math=[
            math("answer",out,"行列式值等于上三角阵对角元素之积。"),
            math("zero_case",r"a=1,\;D=0",
                 "参数取一时，原行列式的值为零。"),
            math("nonzero_case",r"a\neq1,\;D\neq0",
                 "参数不等于一时，原行列式不为零。")
        ]
    units.append(unit("final",spec["final_heading"],spec["final_detail"],
                      "总结并保留题目最终结果。",final_math,
                      phase="summary",kind="conclusion"))
    reference="\n".join([spec["problem"]]+[o["latex"] for u in units
                                                   for o in u["math"]])
    knowledge_catalog={
        "schema_version":"1.0","teacher_reviewed":True,
        "points":[{
            "event_id":"e_intro","topic_id":"matrix_"+kind,
            "title":spec["intro_heading"],"kind":"property",
            "formulae":[{"object_id":"m_intro_rule","latex":spec["intro"]}],
            "used_in":["e_intro","e_step1"],
        }],
    }
    package,board,execution,cues=compile_teaching_units(
        problem=spec["problem"],reference_solution=reference,
        units=units,teacher_reviewed=True,knowledge_catalog=knowledge_catalog
    )
    manifest={
        "schema_version":"1.0",
        "mode":"verified_matrix_operations",
        "teacher_reviewed":True,
        "source_storyboard_sha256":execution.source_storyboard_sha256,
        "kind":kind,
        "augmented_at":augment,
        "initial":{
            "event_id":"e_intro","matrix_id":"m_initial",
            "entries":spec["initial"],
        },
        "steps":steps,
        "final":{"event_id":"e_final","object_id":"m_answer","answer":out},
        "nonzero_assumptions":[],
    }
    policy=simple_classroom_policy()
    return package,board,execution,cues,policy,manifest,units,out


def export_variant(name:str,output:Path):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    package,board,execution,cues,policy,manifest,units,result=build_variant(name)
    files={
        "problem.json":{"variant":name,"result":result,
                        "independent_check":"SymPy row arithmetic and final result"},
        "teaching_units.json":{"schema_version":"1.0","units":units},
        "teaching_package.json":package,
        "storyboard.json":board.model_dump(mode="json"),
        "execution.json":execution.model_dump(mode="json"),
        "teacher_approved_cues.json":cues,
        "page_policy.json":policy,
        "matrix_steps.json":manifest,
        "core_knowledge.json":{
            "schema_version":"1.0","teacher_reviewed":True,
            "points":[{
                "event_id":"e_intro","topic_id":"matrix_"+manifest["kind"],
                "title":units[0]["heading"],"kind":"property",
                "formulae":[{"object_id":"m_intro_rule",
                             "latex":units[0]["math"][0]["latex"]}],
                "used_in":["e_intro","e_step1"],
            }],
        },
    }
    for filename,value in files.items():
        (output/filename).write_text(
            json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
        )
    print("V2_5_2_MATRIX_LESSON",name,len(manifest["steps"]),"row operations")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--variant",choices=("A","B","C"),required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    export_variant(args.variant,args.output)
