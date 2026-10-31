"""V2.5.2: teacher-reviewed, algebra-verified row-operation source contract.

An operation is NOT a visual tween inferred from two similar matrices. Every
before matrix, canonical operation label, and after matrix comes from a genuine
source MathTex object. SymPy verifies the arithmetic, while the animation
planner verifies immutable source order and safe on-board staging.

Only finite rational/symbolic entries formed from arithmetic and single-letter
parameters are accepted. No arbitrary sympify strings or executable TeX.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from .longboard_plan import LongboardError, _sources
from .mathtex_renderer import validate_math_latex


def _sympy():
    try:
        import sympy as s
    except ImportError as exc:
        raise LongboardError(
            "MATRIX_SYMPY_REQUIRED: install animation_engine[matrix]"
        ) from exc
    return s


def parse_expr(source: str):
    """Parse only safe arithmetic trees, never Python calls, attributes or code."""
    s = _sympy()
    if not isinstance(source, str) or not 1 <= len(source) <= 70:
        raise LongboardError("MATRIX_UNSAFE_EXPRESSION")
    try:
        root = ast.parse(source, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise LongboardError("MATRIX_UNSAFE_EXPRESSION") from exc

    def parse(node, depth=0):
        if depth > 14:
            raise LongboardError("MATRIX_EXPRESSION_DEPTH")
        if isinstance(node, ast.Constant) and type(node.value) is int:
            if abs(node.value) > 100000:
                raise LongboardError("MATRIX_LARGE_CONSTANT")
            return s.Integer(node.value)
        if isinstance(node, ast.Name) and len(node.id) == 1 and node.id.isascii() and node.id.islower():
            return s.Symbol(node.id)
        if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub):
            a = parse(node.operand, depth+1)
            return a if isinstance(node.op, ast.UAdd) else -a
        if isinstance(node, ast.BinOp) and type(node.op) in (
                ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow):
            a, b = parse(node.left, depth+1), parse(node.right, depth+1)
            if isinstance(node.op, ast.Add):
                return a+b
            if isinstance(node.op, ast.Sub):
                return a-b
            if isinstance(node.op, ast.Mult):
                return a*b
            if isinstance(node.op, ast.Div):
                if b == 0:
                    raise LongboardError("MATRIX_ZERO_DIVISOR")
                return a/b
            if not b.is_Integer or abs(int(b)) > 6:
                raise LongboardError("MATRIX_POWER_UNSAFE")
            if a == 0 and b < 0:
                raise LongboardError("MATRIX_ZERO_DIVISOR")
            return a**b
        raise LongboardError("MATRIX_UNSAFE_EXPRESSION")
    result=parse(root.body)
    if len(str(result)) > 150:
        raise LongboardError("MATRIX_EXPRESSION_TOO_COMPLEX")
    return result


def _equal(a,b):
    s=_sympy()
    return s.simplify(a-b)==0


def _tex(x) -> str:
    return _sympy().latex(x).replace(" ", "")


def matrix_latex(entries, *, augmented_at=None, determinant=False) -> str:
    """Canonical MathTex source, including optional augmented-column divider."""
    s=_sympy()
    m=_matrix(entries)
    rows, cols=m.shape
    if determinant and augmented_at is not None:
        raise LongboardError("MATRIX_DETERMINANT_AUGMENTED")
    if augmented_at is not None:
        if not isinstance(augmented_at,int) or not 0<augmented_at<cols:
            raise LongboardError("MATRIX_BAD_AUGMENTATION")
        spec="c"*augmented_at+"|"+"c"*(cols-augmented_at)
        pre=rf"\begin{{array}}{{{spec}}}"
        post=r"\end{array}"
    else:
        env="vmatrix" if determinant else "bmatrix"
        pre=rf"\begin{{{env}}}"
        post=rf"\end{{{env}}}"
    body=r"\\".join("&".join(_tex(m[i,j]) for j in range(cols))
                      for i in range(rows))
    result=pre+body+post
    validate_math_latex(result)
    return result


def _matrix(entries):
    s=_sympy()
    if (not isinstance(entries,list) or not 1<=len(entries)<=5 or
            any(not isinstance(row,list) for row in entries)):
        raise LongboardError("MATRIX_INVALID_ROWS")
    n=len(entries[0])
    if not 1<=n<=8 or any(len(row)!=n for row in entries):
        raise LongboardError("MATRIX_INVALID_SHAPE")
    if not all(isinstance(v,str) for row in entries for v in row):
        raise LongboardError("MATRIX_ENTRY_STRING_REQUIRED")
    return s.Matrix([[parse_expr(cell) for cell in row] for row in entries])


def _check_denominators(m, assumptions: list[str]):
    s=_sympy()
    assumed=[parse_expr(x) for x in assumptions]
    for item in list(m):
        den=s.denom(s.cancel(item))
        if den==1 or den.is_number and den!=0:
            continue
        if not any(s.simplify(den/condition).is_number and
                   s.simplify(den/condition)!=0
                   for condition in assumed if condition!=0):
            raise LongboardError("MATRIX_UNPROVEN_NONZERO_DENOMINATOR")


def operation_latex(op: dict) -> str:
    if not isinstance(op,dict) or op.get("kind") not in (
            "add_scaled_row","scale_row","swap_rows"):
        raise LongboardError("MATRIX_UNKNOWN_OPERATION")
    k=op["kind"]
    if k=="swap_rows":
        if set(op)!={"kind","first","second"}:
            raise LongboardError("MATRIX_OPERATION_FIELDS")
        return rf"R_{{{op['first']}}}\leftrightarrow R_{{{op['second']}}}"
    if k=="scale_row":
        if set(op)!={"kind","target","factor"}:
            raise LongboardError("MATRIX_OPERATION_FIELDS")
        f=parse_expr(op["factor"])
        return rf"R_{{{op['target']}}}\leftarrow({_tex(f)})R_{{{op['target']}}}"
    if set(op)!={"kind","target","source","factor"}:
        raise LongboardError("MATRIX_OPERATION_FIELDS")
    f=parse_expr(op["factor"])
    sign="-" if f.is_negative else "+"
    coeff=_tex(-f if f.is_negative else f)
    return rf"R_{{{op['target']}}}\leftarrow R_{{{op['target']}}}{sign}({coeff})R_{{{op['source']}}}"


def _apply(m, op: dict, assumptions: list[str]):
    s=_sympy()
    out=m.copy()
    count=m.rows
    if op["kind"]=="swap_rows":
        a,b=op["first"],op["second"]
        if type(a) is not int or type(b) is not int or not 1<=a<=count or not 1<=b<=count or a==b:
            raise LongboardError("MATRIX_INVALID_ROW_INDEX")
        out.row_swap(a-1,b-1)
    else:
        t=op["target"]
        if type(t) is not int or not 1<=t<=count:
            raise LongboardError("MATRIX_INVALID_ROW_INDEX")
        factor=parse_expr(op["factor"])
        _check_denominators(s.Matrix([factor]), assumptions)
        if op["kind"]=="scale_row":
            if factor==0 or s.simplify(factor)==0:
                raise LongboardError("MATRIX_ZERO_ROW_SCALE")
            out.row_op(t-1,lambda v,j:s.cancel(factor*v))
        else:
            src=op["source"]
            if type(src) is not int or not 1<=src<=count or src==t:
                raise LongboardError("MATRIX_INVALID_ROW_INDEX")
            previous=list(m.row(src-1))
            out.row_op(t-1,lambda v,j:s.cancel(v+factor*previous[j]))
    _check_denominators(out,assumptions)
    return out


@dataclass(frozen=True)
class MatrixStep:
    event_id: str
    before_id: str
    operation_id: str
    after_id: str
    op: dict
    after: Any


@dataclass(frozen=True)
class MatrixLesson:
    kind: str
    augmented_at: int | None
    determinant: bool
    initial_event_id: str
    initial_id: str
    initial_matrix: Any
    steps: tuple[MatrixStep,...]
    final_id: str
    expected_answer: Any

    def for_event(self,event_id):
        return next((x for x in self.steps if x.event_id==event_id),None)

    def info(self,event_id):
        stage=("matrix_initial" if event_id==self.initial_event_id
               else "matrix_operation" if self.for_event(event_id)
               else "matrix_conclusion")
        return {"matrix_stage":stage,
                "row_operation":(self.for_event(event_id).op
                                 if self.for_event(event_id) else None)}


def checked_matrix_steps(payload,board,execution) -> MatrixLesson:
    from visual_director.models import StoryboardPlan
    from .models import ExecutionPlan
    b=StoryboardPlan.model_validate(board)
    e=ExecutionPlan.model_validate(execution)
    required={"schema_version","mode","teacher_reviewed",
              "source_storyboard_sha256","kind","augmented_at",
              "initial","steps","final","nonzero_assumptions"}
    if (not isinstance(payload,dict) or set(payload)!=required or
            payload.get("schema_version")!="1.0" or
            payload.get("mode")!="verified_matrix_operations" or
            payload.get("teacher_reviewed") is not True):
        raise LongboardError("MATRIX_INVALID_MANIFEST")
    if e.source_storyboard_sha256!=payload["source_storyboard_sha256"]:
        raise LongboardError("MATRIX_SOURCE_HASH")
    kind=payload["kind"]
    if kind not in ("linear_system","inverse","determinant"):
        raise LongboardError("MATRIX_UNSUPPORTED_KIND")
    augmented_at=payload["augmented_at"]
    if type(augmented_at) is not int and augmented_at is not None:
        raise LongboardError("MATRIX_BAD_AUGMENTATION")
    determinant=kind=="determinant"
    if determinant and augmented_at is not None:
        raise LongboardError("MATRIX_DETERMINANT_AUGMENTED")
    assumptions=payload["nonzero_assumptions"]
    if not isinstance(assumptions,list) or len(assumptions)>8 or any(
            not isinstance(x,str) for x in assumptions):
        raise LongboardError("MATRIX_BAD_ASSUMPTIONS")
    for assumption in assumptions:
        parsed=parse_expr(assumption)
        if parsed==0 or not parsed.free_symbols:
            raise LongboardError("MATRIX_BAD_ASSUMPTIONS")
    scenes=list(b.scenes)
    ids=[x.event_id for x in scenes]
    if len(ids)!=len(set(ids)):
        raise LongboardError("MATRIX_DUPLICATE_EVENT")
    sources=_sources(e)
    written={}
    for scene in e.scenes:
        written[scene.event_id]=[a.object_id for a in scene.actions
                                if a.kind in ("progressive_write","restore")
                                and a.to_region!="question"]
    def source_math(event_id, mid):
        if mid not in sources or mid not in written.get(event_id,[]):
            raise LongboardError("MATRIX_UNKNOWN_SOURCE: "+str(mid))
        return sources[mid]["latex"]
    initial=payload["initial"]
    if not isinstance(initial,dict) or set(initial)!={"event_id","matrix_id","entries"}:
        raise LongboardError("MATRIX_INITIAL_FIELDS")
    if not ids or ids[0]!=initial["event_id"]:
        raise LongboardError("MATRIX_INITIAL_NOT_FIRST")
    m=_matrix(initial["entries"])
    _check_denominators(m,assumptions)
    if augmented_at is not None and not 0<augmented_at<m.cols:
        raise LongboardError("MATRIX_BAD_AUGMENTATION")
    if determinant and m.rows!=m.cols:
        raise LongboardError("MATRIX_NON_SQUARE_DETERMINANT")
    if kind=="inverse" and (m.cols!=2*m.rows or augmented_at!=m.rows):
        raise LongboardError("MATRIX_INVERSE_AUGMENTATION")
    if kind=="linear_system" and (augmented_at!=m.cols-1 or m.rows!=augmented_at):
        raise LongboardError("MATRIX_SYSTEM_SHAPE")
    if source_math(initial["event_id"],initial["matrix_id"])!=matrix_latex(
            initial["entries"],augmented_at=augmented_at,determinant=determinant):
        raise LongboardError("MATRIX_INITIAL_TEX_NOT_CANONICAL")
    allsteps=payload["steps"]
    if not isinstance(allsteps,list) or not 1<=len(allsteps)<=12:
        raise LongboardError("MATRIX_STEP_COUNT")
    if len(ids)!=len(allsteps)+2:
        raise LongboardError("MATRIX_EVENTS_UNCOVERED")
    prev=m
    checked=[]
    for idx,raw in enumerate(allsteps):
        fields={"event_id","before_id","operation_id","after_id",
                "before","after","operation"}
        if not isinstance(raw,dict) or set(raw)!=fields:
            raise LongboardError("MATRIX_STEP_FIELDS")
        eid=raw["event_id"]
        if eid!=ids[idx+1] or len(written[eid])!=3 or written[eid]!=[
                raw["before_id"],raw["operation_id"],raw["after_id"]]:
            raise LongboardError("MATRIX_STEP_WRITE_ORDER")
        before=_matrix(raw["before"])
        after=_matrix(raw["after"])
        if before.shape!=prev.shape or after.shape!=prev.shape:
            raise LongboardError("MATRIX_STEP_SHAPE_CHANGED")
        if any(not _equal(before[i,j],prev[i,j])
               for i in range(prev.rows) for j in range(prev.cols)):
            raise LongboardError("MATRIX_BEFORE_STATE_MISMATCH")
        op=raw["operation"]
        opname=operation_latex(op)
        if source_math(eid,raw["operation_id"])!=opname:
            raise LongboardError("MATRIX_OPERATION_TEX_MISMATCH")
        if source_math(eid,raw["before_id"])!=matrix_latex(
                raw["before"],augmented_at=augmented_at,determinant=determinant):
            raise LongboardError("MATRIX_BEFORE_TEX_MISMATCH")
        if source_math(eid,raw["after_id"])!=matrix_latex(
                raw["after"],augmented_at=augmented_at,determinant=determinant):
            raise LongboardError("MATRIX_AFTER_TEX_MISMATCH")
        actual=_apply(prev,op,assumptions)
        if any(not _equal(after[i,j],actual[i,j])
               for i in range(prev.rows) for j in range(prev.cols)):
            raise LongboardError("MATRIX_FALSE_ROW_TRANSFORMATION")
        checked.append(MatrixStep(
            eid,raw["before_id"],raw["operation_id"],raw["after_id"],op,after
        ))
        prev=after
    final=payload["final"]
    if not isinstance(final,dict) or set(final)!={"event_id","object_id","answer"}:
        raise LongboardError("MATRIX_FINAL_FIELDS")
    if final["event_id"]!=ids[-1] or final["object_id"] not in written[ids[-1]]:
        raise LongboardError("MATRIX_FINAL_SOURCE")
    # The final answer MUST match mathematics, not just a manually asserted
    # payload value; check the same original matrix that starts the video.
    s=_sympy()
    if determinant:
        expected=s.factor(m.det())
        if any(not _equal(prev[i,j],prev[i,j]) for i in range(prev.rows) for j in range(prev.cols)):
            raise LongboardError("MATRIX_INVALID_FINAL")
        # For the MVP determinant example, only determinant-preserving row
        # additions are permitted. No silent sign/scaling changes.
        if any(st.op["kind"]!="add_scaled_row" for st in checked):
            raise LongboardError("MATRIX_DETERMINANT_FACTOR_NOT_EXPLAINED")
        final_tex="D="+_tex(expected)
    elif kind=="inverse":
        a=m[:,:m.rows]
        if a.det()==0:
            raise LongboardError("MATRIX_SINGULAR_INVERSE")
        if prev[:,:m.rows]!=s.eye(m.rows) or prev[:,m.rows:]!=a.inv():
            raise LongboardError("MATRIX_INVERSE_NOT_REDUCED")
        expected=a.inv()
        entries=[[str(expected[i,j]) for j in range(expected.cols)]
                 for i in range(expected.rows)]
        final_tex=r"A^{-1}="+matrix_latex(entries)
    else:
        a=m[:,:augmented_at]
        bvec=m[:,augmented_at]
        if a.det()==0 or prev[:,:augmented_at]!=s.eye(augmented_at):
            raise LongboardError("MATRIX_SYSTEM_NOT_REDUCED")
        expected=a.inv()*bvec
        if prev[:,augmented_at]!=expected:
            raise LongboardError("MATRIX_SYSTEM_WRONG_SOLUTION")
        final_tex=r"\begin{aligned}" + r"\\".join(
            f"{'xyzuvw'[i]}={_tex(expected[i])}" for i in range(len(expected))
        )+r"\end{aligned}"
    if final["answer"]!=final_tex or source_math(final["event_id"],final["object_id"])!=final_tex:
        raise LongboardError("MATRIX_FINAL_ANSWER_MISMATCH")
    # Reject any unmanifested matrix scene, and any unapproved diagram/proof.
    for scene in scenes:
        if scene.diagram is not None or scene.layout in ("diagram_split","proof_scroll"):
            raise LongboardError("MATRIX_FOREIGN_SPECIAL_LAYOUT")
        if scene.layout=="matrix_compare" and scene.event_id not in {
                initial["event_id"],*(st.event_id for st in checked)}:
            raise LongboardError("MATRIX_UNDECLARED_MATRIX_SCENE")
    return MatrixLesson(
        kind,augmented_at,determinant,initial["event_id"],
        initial["matrix_id"],m,tuple(checked),final["object_id"],expected
    )
