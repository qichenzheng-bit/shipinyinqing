"""Compile approved mathematical LaTeX into genuine Manim MathTex glyphs.

Only for controlled offline educational inputs. Do not expose an on-host
TeX compiler to arbitrary Internet users; defense-in-depth isolation is
required before any service deployment.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from manim import MathTex


class MathTexRenderError(ValueError):
    """Unsafe LaTeX, unavailable TeX environment, or genuine compile failure."""


@dataclass(frozen=True)
class MathGlyphMetrics:
    width_units: float
    height_units: float


# Small, intentionally conservative mathematical vocabulary. Grow via tests
# and review as actual teacher content requires, never silently expand to
# arbitrary programmable TeX. The compiler still needs process isolation for
# untrusted sources.
_ALLOWED_MACROS = frozenset({
    "frac", "dfrac", "tfrac", "sqrt", "sin", "cos", "tan", "cot",
    "arcsin", "arccos", "arctan", "ln", "log", "exp",
    "lim", "limits", "displaystyle", "textstyle", "to", "rightarrow",
    "leftarrow", "infty", "int", "iint", "iiint", "oint",
    "sum", "prod", "partial", "nabla", "cdot", "times", "pm",
    "le", "leq", "ge", "geq", "neq", "ne", "approx", "sim",
    "equiv", "subset", "subseteq", "in", "forall", "exists",
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon",
    "theta", "lambda", "mu", "nu", "pi", "sigma", "omega",
    "Gamma", "Delta", "Sigma", "Omega", "mathbb", "mathbf",
    "mathrm", "mathcal", "overline", "bar", "hat", "widehat",
    "vec", "overrightarrow", "underbrace", "overbrace",
    "left", "right", "bigl", "bigr", "Bigl", "Bigr",
    "begin", "end", "dots", "cdots", "ldots",
    "det", "leftrightarrow", "longrightarrow", "mid",
})
_ALLOWED_ENVIRONMENTS = frozenset({
    "matrix", "pmatrix", "bmatrix", "vmatrix", "Vmatrix", "array",
    "aligned", "alignedat", "cases", "smallmatrix",
})
_CONTROL = re.compile(r"\\([A-Za-z@]+|[^A-Za-z@])")
_ENVS = re.compile(r"\\(begin|end)\s*\{([^{}]+)\}")


def validate_math_latex(latex: str) -> None:
    if not isinstance(latex, str) or not latex.strip():
        raise MathTexRenderError("UNSAFE_TEX: empty mathematical input")
    if len(latex) > 2500 or any(ord(ch) > 127 for ch in latex):
        raise MathTexRenderError("UNSAFE_TEX: oversized or non-ASCII math input")
    if any(ch in latex for ch in ("%", "#", "$", "~", "\x00")):
        raise MathTexRenderError("UNSAFE_TEX: TeX comments/macros/parameters prohibited")
    if latex.count("{") != latex.count("}"):
        raise MathTexRenderError("UNSAFE_TEX: unbalanced curly braces")
    # Manim may silently rewrite unmatched delimiters (e.g. \\left to
    # \\big) before LaTeX compilation; reject the source rather than render
    # a subtly different mathematical expression.
    lefts = len(re.findall(r"\\left(?![A-Za-z])", latex))
    rights = len(re.findall(r"\\right(?![A-Za-z])", latex))
    if lefts != rights:
        raise MathTexRenderError("TEX_COMPILE_FAILED: unmatched \\left/\\right delimiters")


    env_stack: list[str] = []
    for match in _ENVS.finditer(latex):
        kind, name = match.groups()
        if name not in _ALLOWED_ENVIRONMENTS:
            raise MathTexRenderError(f"UNSAFE_TEX: environment {name!r} not allowed")
        if kind == "begin":
            env_stack.append(name)
        elif not env_stack or env_stack.pop() != name:
            raise MathTexRenderError("UNSAFE_TEX: mismatched environment delimiters")
    if env_stack:
        raise MathTexRenderError("UNSAFE_TEX: unterminated math environment")

    # Reject macro definitions, file I/O, execution, catcode changes and other
    # programmable TeX commands BEFORE the external compiler is invoked.
    for token in _CONTROL.findall(latex):
        if token.isalpha():
            if token not in _ALLOWED_MACROS:
                raise MathTexRenderError(f"UNSAFE_TEX: command \\{token} not permitted")
        elif token not in ("\\", ",", "!", ";", ":", " "):
            raise MathTexRenderError("UNSAFE_TEX: unsupported TeX control symbol")


def build_measured_mathtex(
    latex: str, *, ink: str = "#1E293B"
) -> tuple[MathTex, MathGlyphMetrics]:
    validate_math_latex(latex)
    if not shutil.which("latex") or not shutil.which("dvisvgm"):
        raise MathTexRenderError("LATEX_ENV_UNAVAILABLE: latex and dvisvgm are required")
    try:
        from manim import MathTex
    except ImportError as exc:
        raise MathTexRenderError("LATEX_ENV_UNAVAILABLE: install animation_engine[render]") from exc
    try:
        obj = MathTex(latex, color=ink)
    except Exception as exc:
        raise MathTexRenderError(
            f"TEX_COMPILE_FAILED: {type(exc).__name__}: {str(exc)[:220]}"
        ) from exc
    metrics = MathGlyphMetrics(width_units=float(obj.width), height_units=float(obj.height))
    if metrics.width_units <= 0 or metrics.height_units <= 0:
        raise MathTexRenderError("TEX_COMPILE_FAILED: empty glyph geometry")
    return obj, metrics
