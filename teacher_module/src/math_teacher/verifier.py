"""Conservative algebraic checks; NOT a general proof assistant or LaTeX verifier.

Only permitted expression AST nodes are evaluated; never use sympify/eval on
untrusted model output. Quotient identities and conditional statements remain
undetermined because domain restrictions require additional proof.
"""
from __future__ import annotations
import ast
import operator

from sympy import Symbol, cos, exp, log, simplify, sin, sqrt
from .models import MathCheckRequest, MathVerification

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Pow: operator.pow}
FUNCTIONS = {"sin": sin, "cos": cos, "exp": exp, "log": log, "sqrt": sqrt}


def _safe_sympy(expr: str):
    if len(expr) > 240:
        raise ValueError("expression too long")
    root = ast.parse(expr, mode="eval")
    nodes = list(ast.walk(root))
    if len(nodes) > 75:
        raise ValueError("expression too complex")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) is int and abs(node.value) <= 100000:
            return node.value
        if isinstance(node, ast.Name) and node.id.isalpha() and len(node.id) <= 8 and node.id not in FUNCTIONS:
            return Symbol(node.id, real=True)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            if type(node.op) not in OPS:
                raise ValueError("unsupported operator or domain-dependent division")
            if isinstance(node.op, ast.Pow):
                if not isinstance(node.right, ast.Constant) or type(node.right.value) is not int or not 0 <= node.right.value <= 8:
                    raise ValueError("power is not a bounded non-negative integer")
            return OPS[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and len(node.args) == 1 and not node.keywords:
            return FUNCTIONS[node.func.id](visit(node.args[0]))
        raise ValueError("unsupported expression syntax")
    return visit(root)


def verify_math_check(request: MathCheckRequest) -> MathVerification:
    try:
        left, right = _safe_sympy(request.lhs_expr), _safe_sympy(request.rhs_expr)
        diff = simplify(left - right)
        if diff == 0:
            return MathVerification(check_id=request.check_id, step_id=request.step_id, status="verified", explanation="Bounded algebraic identity checked; any external hypotheses/theorem applicability still require separate review")
        if diff.is_zero is False:
            return MathVerification(check_id=request.check_id, step_id=request.step_id, status="failed", explanation="The expressions are not algebraically identical under the supported checker")
        return MathVerification(check_id=request.check_id, step_id=request.step_id, status="undetermined", explanation="Symbolic zero test inconclusive")
    except (ValueError, SyntaxError, TypeError, OverflowError, RecursionError, AttributeError, ZeroDivisionError) as exc:
        return MathVerification(check_id=request.check_id, step_id=request.step_id, status="undetermined", explanation=str(exc))
