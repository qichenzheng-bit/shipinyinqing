"""Real math + Chinese question compositor for the existing 2.3 layout PNG.

Only approved teacher question text is used. Chinese text is drawn with a real
CJK font; mathematical expressions are genuine Manim MathTex objects, not
plain-text imitations. No made-up subtitles, audio, speech timing or equations.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .adaptive_layout import AdaptiveLayoutError, render_layout_png
from .mathtex_renderer import validate_math_latex


_PUNCTUATION = frozenset(".。！？!?．")
_CJK_FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
)
_HEADER_SAFE_PX = 6
_MIN_HEADER_SCALE = 0.90


def _source_parts(question: str) -> tuple[str, str, str]:
    """Conservative source-only split. Reject ambiguous mixed content."""
    if not isinstance(question, str) or not question.strip():
        raise AdaptiveLayoutError("HEADER_SOURCE_EMPTY")
    math_begin = question.find("\\")
    if math_begin == -1:
        return question, "", ""
    chinese = question[:math_begin]
    candidate = question[math_begin:]
    # Non-ASCII must remain in text instead of being forged as MathTex.
    if any(ord(c) > 127 for c in candidate):
        raise AdaptiveLayoutError(
            "HEADER_MIXED_SEGMENTS_UNSUPPORTED: supply approved text/math segments"
        )
    suffix = ""
    while candidate and candidate[-1] in _PUNCTUATION:
        suffix = candidate[-1] + suffix
        candidate = candidate[:-1]
    if not candidate.strip():
        raise AdaptiveLayoutError("HEADER_EMPTY_MATH")
    validate_math_latex(candidate)
    if chinese + candidate + suffix != question:
        raise AdaptiveLayoutError("HEADER_SOURCE_CHANGED")
    return chinese, candidate, suffix


def _font(size: int):
    from PIL import ImageFont
    for path in _CJK_FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise AdaptiveLayoutError("CJK_FONT_UNAVAILABLE: install fonts-noto-cjk")


def render_classroom_board_png(
    storyboard, execution, *, event_id: str, output_png: Path, output_json: Path,
    pixel_width: int = 1280, pixel_height: int = 720,
) -> dict:
    """Composite a fixed, source-exact header onto real, verified MathTex board.

    The rendering takes place only when the formula scene already fits. Header
    height is respected without moving board equations or hiding captions.
    """
    from PIL import Image, ImageDraw
    from visual_director.models import StoryboardPlan

    board = StoryboardPlan.model_validate(storyboard)
    output_png, output_json = Path(output_png), Path(output_json)
    if (output_png.resolve() == output_json.resolve()
            or output_png.suffix.lower() != ".png"
            or output_json.suffix.lower() != ".json"):
        raise AdaptiveLayoutError("INVALID_OUTPUT")
    text_part, math_part, suffix = _source_parts(board.header.text)

    with tempfile.TemporaryDirectory(prefix="classroom-preview-") as temp:
        work = Path(temp)
        # This first cross-validates the storyboard against its execution and
        # refuses to produce a false "successful" scene on CUT_REQUIRED.
        old_manifest = render_layout_png(
            board, execution, event_id=event_id,
            output_png=work / "math.png", output_json=work / "math.json",
            pixel_width=pixel_width, pixel_height=pixel_height,
        )
        math_overlay = None
        math_width = math_height = 0.0
        if math_part:
            try:
                from manim import Camera, MathTex, tempconfig
            except ImportError as exc:
                raise AdaptiveLayoutError("LATEX_ENV_UNAVAILABLE") from exc
            fw, fh = pixel_width / pixel_height * 8.0, 8.0
            with tempconfig({
                "pixel_width": pixel_width, "pixel_height": pixel_height,
                "frame_width": fw, "frame_height": fh,
                "background_color": board.theme.background,
            }):
                glyph = MathTex(math_part, color=board.theme.ink, font_size=34)
                math_width = glyph.width * pixel_height / 8.0
                math_height = glyph.height * pixel_height / 8.0
                glyph.move_to([0, 0, 0])
                cam = Camera()
                cam.capture_mobjects([glyph])
                raw = cam.get_image().convert("RGB")
                left = int((glyph.get_left()[0] / fw + .5) * pixel_width) - 2
                right = int((glyph.get_right()[0] / fw + .5) * pixel_width) + 3
                top = int((.5 - glyph.get_top()[1] / fh) * pixel_height) - 2
                bottom = int((.5 - glyph.get_bottom()[1] / fh) * pixel_height) + 3
                math_overlay = raw.crop((left, top, right, bottom))

        image = Image.open(work / "math.png").convert("RGB")
        d = ImageDraw.Draw(image)
        z = old_manifest["header"]
        # The same immutable header height defines the board's top boundary;
        # title is never permitted to spill into a working formula.
        original_zone = board.scenes[
            next(i for i, s in enumerate(board.scenes) if s.event_id == event_id)
        ].regions["question"]
        left = original_zone.x * pixel_width
        top = original_zone.y * pixel_height
        width = original_zone.w * pixel_width
        height = original_zone.h * pixel_height
        # Equation text in the question is part of the pedagogical prompt.
        # Never make it tiny; reject if it would require more than 10% shrink.
        font = _font(31 if pixel_height >= 600 else max(17, pixel_height // 25))
        cbox = d.textbbox((0, 0), text_part, font=font)
        sbox = d.textbbox((0, 0), suffix, font=font)
        tw, th = cbox[2] - cbox[0], cbox[3] - cbox[1]
        sw, sh = sbox[2] - sbox[0], sbox[3] - sbox[1]
        m_w = math_overlay.width if math_overlay else 0
        m_h = math_overlay.height if math_overlay else 0
        max_width = width - 2 * _HEADER_SAFE_PX
        max_height = height - 2 * _HEADER_SAFE_PX
        required_width = tw + m_w + sw + (18 if math_overlay else 0)
        required_height = max(th, sh, m_h)
        factor = min(1.0, max_width / max(required_width, 1),
                     max_height / max(required_height, 1))
        if factor < _MIN_HEADER_SCALE - 1e-8:
            raise AdaptiveLayoutError(
                "HEADER_OVERFLOW: approved question needs dedicated layout; "
                f"required={required_width:.1f}x{required_height:.1f}, "
                f"available={max_width:.1f}x{max_height:.1f}"
            )
        if factor < 1:
            font = _font(round(font.size * factor))
            cbox = d.textbbox((0, 0), text_part, font=font)
            sbox = d.textbbox((0, 0), suffix, font=font)
            tw, th = cbox[2]-cbox[0], cbox[3]-cbox[1]
            sw, sh = sbox[2]-sbox[0], sbox[3]-sbox[1]
            if math_overlay:
                math_overlay = math_overlay.resize(
                    (round(math_overlay.width * factor),
                     round(math_overlay.height * factor)), Image.Resampling.LANCZOS)
                m_w, m_h = math_overlay.size
            required_width = tw+m_w+sw+(18 if math_overlay else 0)
            required_height = max(th, sh, m_h)
            if required_width > max_width + 1 or required_height > max_height + 1:
                raise AdaptiveLayoutError("HEADER_OVERFLOW: conservative font size")
        if z["align"] == "center":
            x = left + (width - required_width)/2
        else:
            x = left + _HEADER_SAFE_PX
        baseline_mid = top + height/2
        chinese_xy = (round(x), round(baseline_mid-th/2-cbox[1]))
        if text_part:
            d.text(chinese_xy, text_part, font=font, fill=board.theme.ink)
        x += tw
        if math_overlay:
            x += 9
            y = round(baseline_mid-m_h/2)
            image.paste(math_overlay, (round(x), y))
            x += m_w + 9
        if suffix:
            d.text((round(x),round(baseline_mid-sh/2-sbox[1])),
                   suffix, font=font, fill=board.theme.ink)
        # Readable frame contract: no question pixel enters board working region.
        if required_width > width or required_height > height:
            raise AdaptiveLayoutError("HEADER_OVERFLOW: layout violated region")

        manifest = {
            **old_manifest,
            "preview_kind": "real_mathtex_board_and_composed_question_png",
            "header_caption_status": "question_rendered_subtitles_reserved_not_audio_aligned",
            "question_source_sha256": hashlib.sha256(
                board.header.text.encode("utf-8")
            ).hexdigest(),
            "question_parts": {"chinese": text_part, "math_latex": math_part,
                               "trailing_punctuation": suffix},
            "header_bbox_px": [round(left), round(top), round(width), round(height)],
            "header_mathtex_actual_px": [round(math_width, 2),round(math_height,2)],
            "header_display_scale": round(factor, 5),
            "speech_subtitle_status": "not_rendered_no_audio",
        }
        pending_png = work / "composed.png"
        pending_json = work / "composed.json"
        image.save(pending_png)
        pending_json.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            output_png.parent.mkdir(parents=True, exist_ok=True)
            output_json.parent.mkdir(parents=True, exist_ok=True)
            os.replace(pending_png, output_png)
            os.replace(pending_json, output_json)
        except Exception:
            output_png.unlink(missing_ok=True)
            output_json.unlink(missing_ok=True)
            raise
        return manifest
