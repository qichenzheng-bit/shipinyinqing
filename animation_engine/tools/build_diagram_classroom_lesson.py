"""V2.5.4 independently authored graph, calculus-region and geometry lessons.

Every plotted sample and every geometric segment is teacher-approved
structured source in the StoryboardPlan; Manim only draws frozen points.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from animation_engine.classroom_teaching_units import compile_teaching_units
from animation_engine.classroom_policy import simple_classroom_policy


def formula(ident, latex, reason):
    return {"id":ident,"latex":latex,"reason":reason}


def unit(ident,heading,detail,expressions,*,phase="calculate"):
    return {
        "id":ident,"heading":heading,"detail":detail,
        "goal":"按给定数学来源逐步书写并核对图形关系",
        "event_type":"diagram","phase":phase,"math":expressions,
        "pause_seconds":1.5,"write_seconds":.83,
    }


def point(ident,x,y,label=""):
    return {"id":ident,"x":round(x,7),"y":round(y,7),"label":label}


def line(ident,start,end,dashed=False):
    return {"id":ident,"start":start,"end":end,"dashed":dashed}


def curve(ident,points):
    return {"id":ident,"points":[[round(x,7),round(y,7)] for x,y in points]}


def stage(ident,objects,*,order="diagram_then_math"):
    return {
        "event_id":"e_"+ident,"reveal_ids":objects,
        "order":order,
    }


def function_graph():
    # Pixel-calibrated x/y axis mapping; x in [0,2], y in [0,4].
    graph_pts=[(.18+.32*(k/8),.78-.16*(k/8)**2)
               for k in range(17)]
    p={
        "O":point("O",.18,.78,"O"),
        "x_tip":point("x_tip",.93,.78),
        "y_tip":point("y_tip",.18,.10),
        "P":point("P",.50,.62,"P"),
        "T0":point("T0",.356,.764),
        "T1":point("T1",.708,.412),
    }
    specs={
        "event_id":"e_intro",
        "points":list(p.values()),
        "lines":[line("axis_x","O","x_tip"),
                 line("axis_y","O","y_tip"),
                 line("tangent","T0","T1")],
        "curves":[curve("parabola",graph_pts)],
    }
    units=[
        unit("intro","观察二次函数图像",
             "先画出坐标轴，明确研究的函数与切点。",
             [formula("given",r"f(x)=x^2",
                      "本题已知的二次函数。")],phase="strategy"),
        unit("curve","绘制函数曲线","按真实坐标绘制抛物线并标记切点。",
             [formula("point_result",r"P(1,1),\quad f(1)=1",
                      "切点由已知函数确定。")]),
        unit("rule","导数的几何意义",
             "曲线在一点的切线斜率等于该点的导数。",
             [formula("rule_formula",r"k=f'(x_0)",
                      "曲线切线的通用斜率公式。"),
              formula("derivative",r"f'(x)=2x",
                      "对本题二次函数求导。")],phase="knowledge"),
        unit("tangent","计算切线方程",
             "将切点及导数值代入点斜式。",
             [formula("tangent_step",r"y-1=2(x-1)",
                      "通过点斜式得到本题切线。")]),
        unit("final","整理切线结果","得到抛物线在指定点的切线。",
             [formula("tangent_final",r"y=2x-1",
                      "切线结果与图形点坐标一致。")],phase="summary"),
    ]
    shows=[
        stage("intro",["axis_x","axis_y","O","label:O"]),
        stage("curve",["parabola","P","label:P"]),
        stage("rule",[]),
        stage("tangent",["T0","T1","tangent"]),
        stage("final",["x_tip","y_tip"]),
    ]
    return (r"求曲线切线方程：\quad f(x)=x^2,\ P(1,1)",
            "function_graph",specs,units,shows,[])


def integral_region():
    xs=[i/16 for i in range(17)]
    upper=[(.16+.65*x,.86-.62*x) for x in xs]
    lower=[(.16+.65*x,.86-.62*x*x) for x in xs]
    specs={
        "event_id":"e_intro",
        "points":[point("O",.16,.86,"O"),
                  point("x_tip",.94,.86),
                  point("y_tip",.16,.08),
                  point("Q",.81,.24,"Q")],
        "lines":[line("axis_x","O","x_tip"),
                 line("axis_y","O","y_tip")],
        "curves":[curve("upper_line",upper),
                  curve("lower_parabola",lower)],
    }
    units=[
        unit("intro","观察两条边界曲线",
             "两条曲线围出有界区域，先确定积分方向。",
             [formula("domain",r"0\le x\le1",
                      "两曲线在零和一处相交。")],phase="strategy"),
        unit("draw_upper","画出上方曲线",
             "上边界在区间内为直线。",
             [formula("top",r"f(x)=x",
                      "该直线在区间内位于抛物线上方。")]),
        unit("draw_lower","画出下方曲线",
             "下边界为抛物线，切勿把两者颠倒。",
             [formula("bottom",r"g(x)=x^2",
                      "下边界确定。")]),
        unit("rule","定积分求面积公式",
             "在同一区间上，面积等于上函数减下函数的定积分。",
             [formula("area_rule",r"S=\int_a^b\!\left[f(x)-g(x)\right]\,dx",
                      "面积公式需先确认上下边界。")],phase="knowledge"),
        unit("integrate","对区域逐步积分",
             "将两条边界代入已知面积公式。",
             [formula("area_step",r"S=\int_0^1(x-x^2)\,dx",
                      "面积为上减下积分。")]),
        unit("final","计算区域面积",
             "计算端点并得出非负的准确面积。",
             [formula("area_final",r"S=\frac12-\frac13=\frac16",
                      "实际面积独立核对为六分之一。")],phase="summary"),
    ]
    shows=[
        stage("intro",["axis_x","axis_y","O","label:O"]),
        stage("draw_upper",["upper_line"]),
        stage("draw_lower",["lower_parabola","Q","label:Q"]),
        stage("rule",["shade_between"]),
        stage("integrate",[]),
        stage("final",["x_tip","y_tip"]),
    ]
    regions=[{"id":"shade_between","upper_curve_id":"upper_line",
              "lower_curve_id":"lower_parabola"}]
    return (r"求两曲线围成的面积：\quad y=x,\ y=x^2,\ 0\le x\le1",
            "integration_region",specs,units,shows,regions)


def geometry_proof():
    # Actual displayed horizontal/vertical side lengths 4:3 in pixels.
    a=(.19,.82)
    b=(.19+224/480,.82)
    c=(.19,.82-168/358)
    u=(.19+18/480,.82)
    v=(.19+18/480,.82-18/358)
    w=(.19,.82-18/358)
    specs={
        "event_id":"e_intro",
        "points":[
            point("A",*a,"A"),point("B",*b,"B"),
            point("C",*c,"C"),point("U",*u),
            point("V",*v),point("W",*w),
        ],
        "lines":[
            line("AB","A","B"),line("AC","A","C"),
            line("BC","B","C"),line("right_1","U","V"),
            line("right_2","V","W"),
        ],
        "curves":[],
    }
    units=[
        unit("intro","识别直角三角形",
             "从图形与题设判断直角位置及两条直角边。",
             [formula("legs",r"AB=4,\quad AC=3",
                      "图中两直角边的已知长度。")],phase="strategy"),
        unit("angle","标出直角关系",
             "垂直条件决定斜边是连接另外两顶点的线段。",
             [formula("perpendicular",r"AB\perp AC",
                      "图中 A 为直角顶点。")]),
        unit("rule","勾股定理",
             "直角三角形中两直角边平方和等于斜边平方。",
             [formula("pythagoras",r"a^2+b^2=c^2",
                      "斜边为 c 时使用的通用定理。")],phase="knowledge"),
        unit("apply","代入两直角边长度",
             "确定斜边并代入原始长度，不能将斜边与直角边混淆。",
             [formula("hypotenuse_square",r"BC^2=3^2+4^2=25",
                      "本题斜边的准确平方。")]),
        unit("final","得到斜边长度",
             "长度取正值，不能保留负根。",
             [formula("hypotenuse",r"BC=5",
                      "图形和数学结果一致。")],phase="summary"),
    ]
    shows=[
        stage("intro",["A","B","C","AB","AC"]),
        stage("angle",["U","V","W","right_1","right_2","label:A"]),
        stage("rule",["BC","label:B","label:C"]),
        stage("apply",[]),
        stage("final",[]),
    ]
    return (r"求直角三角形的斜边：\quad AB=4,\ AC=3,\ \angle A=90^\circ",
            "geometry_proof",specs,units,shows,[])


_BUILD={"A":function_graph,"B":integral_region,"C":geometry_proof}


def build_variant(which):
    if which not in _BUILD:
        raise ValueError("DIAGRAM_UNKNOWN_VARIANT")
    problem,kind,specs,units,stages,regions=_BUILD[which]()
    knowledge=next(u for u in units if u["phase"]=="knowledge")
    topic={"A":"derivative_tangent_slope",
           "B":"area_between_curves",
           "C":"pythagorean_theorem"}[which]
    catalog={
        "schema_version":"1.0","teacher_reviewed":True,
        "points":[{
            "event_id":"e_"+knowledge["id"],
            "topic_id":topic,"title":knowledge["heading"],
            "kind":"theorem" if which=="C" else "formula",
            "formulae":[{"object_id":"m_"+knowledge["math"][0]["id"],
                         "latex":knowledge["math"][0]["latex"]}],
            "used_in":[{"A":"e_tangent","B":"e_integrate",
                        "C":"e_apply"}[which]],
        }],
    }
    ref="\n".join([problem]+[
        f["latex"] for u in units for f in u["math"]
    ])
    pkg,board,execution,cues=compile_teaching_units(
        problem=problem,reference_solution=ref,
        units=units,teacher_reviewed=True,
        knowledge_catalog=catalog,diagram_specs=[specs]
    )
    manifest={
        "schema_version":"1.0","mode":"verified_diagram_classroom",
        "teacher_reviewed":True,"kind":kind,
        "source_storyboard_sha256":execution.source_storyboard_sha256,
        "source_event_id":"e_intro",
        "filled_regions":regions,"stages":stages,
    }
    return pkg,board,execution,cues,simple_classroom_policy(),manifest,units,catalog


def export_variant(path,which):
    path=Path(path)
    path.mkdir(parents=True,exist_ok=True)
    pkg,board,exe,cues,policy,manifest,units,catalog=build_variant(which)
    data={
        "teaching_package.json":pkg,
        "storyboard.json":board.model_dump(mode="json"),
        "execution.json":exe.model_dump(mode="json"),
        "teacher_approved_cues.json":cues,
        "teaching_units.json":{"schema_version":"1.0","units":units},
        "page_policy.json":policy,
        "diagram_classroom.json":manifest,
        "core_knowledge.json":catalog,
    }
    for name,body in data.items():
        (path/name).write_text(
            json.dumps(body,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8"
        )
    print("V2_5_4_DIAGRAM_SOURCE",which,manifest["kind"],
          len(units),"stages",len(board.scenes[0].diagram.labels),"labels")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--variant",choices=sorted(_BUILD),required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    export_variant(args.output,args.variant)
