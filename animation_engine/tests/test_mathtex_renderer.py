"""Real (not mocked) MathTex integration tests; require the render extra and TeX."""
import shutil

import pytest

manim = pytest.importorskip("manim")
from manim import MathTex
from animation_engine.mathtex_renderer import (
    MathTexRenderError, build_measured_mathtex, validate_math_latex,
)

@pytest.mark.parametrize("latex", [
    r"\frac{a}{b}",
    r"\displaystyle\lim\limits_{x\to0}\frac{\sin x}{x}",
    r"\int_0^1 x\,dx",
    r"\begin{pmatrix}1&2\\3&4\end{pmatrix}",
])
def test_real_mathtex_measures_nonzero_geometry(latex):
    if not shutil.which("latex") or not shutil.which("dvisvgm"):
        pytest.fail("This integration test requires actual latex and dvisvgm")
    obj, metrics = build_measured_mathtex(latex)
    assert isinstance(obj, MathTex)
    assert metrics.width_units > 0 and metrics.height_units > 0
    assert obj.tex_string == latex
    assert obj.get_color().to_hex().lower() == "#1e293b"


@pytest.mark.parametrize("latex", [
    r"\input{/etc/passwd}", r"\write18{whoami}", r"\usepackage{shellesc}",
    r"\catcode64=11", r"\def\evil{1}", r"\begin{filecontents}{x}",
    r"\csname input\endcsname", r"\special{ps: dangerous}", r"\includegraphics{x}",
])
def test_unsafe_tex_rejected_before_compiling(latex):
    with pytest.raises(MathTexRenderError, match="UNSAFE_TEX"):
        validate_math_latex(latex)


def test_invalid_validated_mathtex_does_not_fall_back_to_plain_text():
    with pytest.raises(MathTexRenderError, match="TEX_COMPILE_FAILED"):
        build_measured_mathtex(r"\left(x")


def test_missing_latex_binary_reports_environment(monkeypatch):
    from animation_engine import mathtex_renderer
    actual = mathtex_renderer.shutil.which
    monkeypatch.setattr(mathtex_renderer.shutil, "which", lambda x: None if x == "latex" else actual(x))
    with pytest.raises(MathTexRenderError, match="LATEX_ENV_UNAVAILABLE"):
        build_measured_mathtex("x+1")
