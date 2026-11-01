"""Source-exact mixed Chinese/math question header, shared by both renderers.

The rendered header preserves every source character and renders mathematical
segments with genuine MathTex. It never converts LaTeX to phonetic text.
"""
from __future__ import annotations

import re
from pathlib import Path

from .adaptive_layout import AdaptiveLayoutError
from .mathtex_renderer import validate_math_latex


_CJK_TEXT = re.compile(r"([\u3400-\u9fff\uf900-\ufaff，。；：、！？（）《》“”‘’]+)")
_MATH_OPERATOR = re.compile(r"[=<>_^+*/]")


def source_header_segments(question: str) -> list[dict[str, str]]:
    """Split mixed source with no omissions; reject any unsafe MathTex macro.

    CJK punctuation and Chinese prose remain literal PIL text. ASCII runs
    containing explicit LaTeX, mathematical operators, or isolated variables
    become true MathTex. Ambiguous English prose stays literal text.
    """
    if not isinstance(question, str) or not question.strip():
        raise AdaptiveLayoutError("HEADER_SOURCE_EMPTY")
    output: list[dict[str, str]] = []

    def add(kind: str, value: str) -> None:
        if not value:
            return
        if output and output[-1]["kind"] == kind:
            output[-1]["value"] += value
        else:
            output.append({"kind": kind, "value": value})

    for chunk in _CJK_TEXT.split(question):
        if not chunk:
            continue
        if _CJK_TEXT.fullmatch(chunk):
            add("text", chunk)
            continue
        match = re.fullmatch(r"(\s*)(.*?)(\s*)", chunk, re.DOTALL)
        assert match is not None
        leading, body, trailing = match.groups()
        has_math = bool(
            "\\" in body or _MATH_OPERATOR.search(body)
            or re.fullmatch(r"[A-Za-z]", body)
        )
        # English words should not silently turn into italic math letters.
        if re.search(r"(?<!\\)[A-Za-z]{3,}", body) and "\\" not in body:
            has_math = False
        if not has_math:
            add("text", chunk)
            continue
        add("text", leading)
        try:
            validate_math_latex(body)
        except ValueError as exc:
            raise AdaptiveLayoutError(str(exc)) from exc
        add("math", body)
        add("text", trailing)
    if "".join(item["value"] for item in output) != question:
        raise AdaptiveLayoutError("HEADER_SOURCE_CHANGED")
    return output


def render_source_header(
    question: str, *, pixel_width: int, pixel_height: int,
    header_box: tuple[float, float, float, float],
    font_loader, font_size: int, math_font_size: int,
    ink_color: str, background: str, align: str = "center",
    min_scale: float = .90, padding: int = 6,
):
    """Return transparent RGBA header and measured, source-grounded metadata."""
    from PIL import Image, ImageDraw, ImageChops
    segments = source_header_segments(question)
    x0, y0, width, height = header_box
    if width <= 0 or height <= 0:
        raise AdaptiveLayoutError("HEADER_INVALID_REGION")
    base_font = font_loader(font_size)
    maths = []
    for item in segments:
        if item["kind"] == "math":
            maths.append(item["value"])
    glyphs = []
    fw, fh = pixel_width / pixel_height * 8.0, 8.0
    if maths:
        try:
            from manim import Camera, MathTex, tempconfig
        except ImportError as exc:
            raise AdaptiveLayoutError("LATEX_ENV_UNAVAILABLE") from exc
        with tempconfig({
            "pixel_width": pixel_width, "pixel_height": pixel_height,
            "frame_width": fw, "frame_height": fh,
            "background_color": background,
        }):
            for latex in maths:
                glyph = MathTex(latex, color=ink_color, font_size=math_font_size)
                glyph.move_to([0, 0, 0])
                left = int((glyph.get_left()[0] / fw + .5) * pixel_width) - 2
                right = int((glyph.get_right()[0] / fw + .5) * pixel_width) + 3
                top = int((.5 - glyph.get_top()[1] / fh) * pixel_height) - 2
                bottom = int((.5 - glyph.get_bottom()[1] / fh) * pixel_height) + 3
                if (left < 0 or top < 0 or right > pixel_width
                        or bottom > pixel_height or right <= left
                        or bottom <= top):
                    raise AdaptiveLayoutError("HEADER_MATH_BOUNDS")
                camera = Camera()
                camera.capture_mobjects([glyph])
                rgb = camera.get_image().convert("RGB").crop(
                    (left, top, right, bottom)
                )
                alpha = ImageChops.difference(
                    rgb, Image.new("RGB", rgb.size, background),
                ).convert("L")
                sprite = rgb.convert("RGBA")
                sprite.putalpha(alpha)
                glyphs.append(sprite)
    math_index = 0

    def make_parts(font):
        nonlocal math_index
        math_index = 0
        result = []
        for item in segments:
            if item["kind"] == "math":
                sprite = glyphs[math_index]
                math_index += 1
            else:
                scratch = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
                bounds = ImageDraw.Draw(scratch).textbbox(
                    (0, 0), item["value"], font=font
                )
                sprite = Image.new("RGBA", (
                    max(1, bounds[2] - bounds[0]),
                    max(1, bounds[3] - bounds[1]),
                ), (0, 0, 0, 0))
                ImageDraw.Draw(sprite).text(
                    (-bounds[0], -bounds[1]), item["value"],
                    fill=ink_color, font=font,
                )
            result.append((item["kind"], sprite))
        return result

    parts = make_parts(base_font)

    def dimensions(items):
        gaps = [
            9 if a[0] != b[0] else 0
            for a, b in zip(items, items[1:])
        ]
        return (sum(p.width for _, p in items) + sum(gaps),
                max(p.height for _, p in items), gaps)

    natural_width, natural_height, gaps = dimensions(parts)
    usable_width, usable_height = width - 2 * padding, height - 2 * padding
    factor = min(1.0, usable_width / max(natural_width, 1),
                 usable_height / max(natural_height, 1))
    if factor < min_scale - 1e-8:
        raise AdaptiveLayoutError(
            "HEADER_OVERFLOW: long question needs teacher-approved header layout"
        )
    if factor < 1.0:
        font = font_loader(max(16, round(font_size * factor)))
        parts = make_parts(font)
        parts = [
            (kind, image.resize((
                max(1, round(image.width * factor)),
                max(1, round(image.height * factor)),
            ), Image.Resampling.LANCZOS)) if kind == "math" else (kind, image)
            for kind, image in parts
        ]
        natural_width, natural_height, gaps = dimensions(parts)
    if natural_width > usable_width + 1 or natural_height > usable_height + 1:
        raise AdaptiveLayoutError("HEADER_OVERFLOW: conservative font adjustment")
    overlay = Image.new("RGBA", (pixel_width, pixel_height), (0, 0, 0, 0))
    current_x = x0 + ((width - natural_width) / 2 if align == "center" else padding)
    mid_y = y0 + height / 2
    for index, (kind, piece) in enumerate(parts):
        dest = (round(current_x), round(mid_y - piece.height / 2))
        if (dest[0] < 0 or dest[1] < 0
                or dest[0] + piece.width > pixel_width
                or dest[1] + piece.height > pixel_height):
            raise AdaptiveLayoutError("HEADER_OVERFLOW: rendered glyph out of frame")
        overlay.alpha_composite(piece, dest)
        current_x += piece.width
        if index < len(gaps):
            current_x += gaps[index]
    alpha_box = overlay.getchannel("A").getbbox()
    if (alpha_box is None or alpha_box[0] < x0 - 2
            or alpha_box[1] < y0 - 2
            or alpha_box[2] > x0 + width + 2
            or alpha_box[3] > y0 + height + 2):
        raise AdaptiveLayoutError("HEADER_OVERFLOW: actual glyphs breached safe region")
    return overlay, {
        "source_segments": segments,
        "math_segments_latex": maths,
        "math_bbox_px": (
            [round(max(p.width for p in glyphs), 2),
             round(max(p.height for p in glyphs), 2)] if glyphs else [0, 0]
        ),
        "header_bbox_px": [round(x0), round(y0), round(width), round(height)],
        "visible_pixel_bbox": list(alpha_box),
        "scale": round(factor, 6),
    }
