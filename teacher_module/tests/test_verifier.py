from math_teacher.models import MathCheckRequest
from math_teacher.verifier import verify_math_check


def check(lhs,rhs):
    return verify_math_check(MathCheckRequest(check_id="c",step_id="s",kind="algebraic_identity",lhs_expr=lhs,rhs_expr=rhs,conditions=[]))


def test_identity():
    assert check("(x-1)*(x+1)","x**2-1").status=="verified"


def test_nonidentity():
    assert check("x+1","x-1").status=="failed"


def test_division_domain_sensitive():
    assert check("x/x","1").status=="undetermined"


def test_disallow_python_execution():
    assert check("__import__('os').system('pwd')","1").status=="undetermined"


def test_disallow_unbounded_power():
    assert check("x**100000","x").status=="undetermined"
