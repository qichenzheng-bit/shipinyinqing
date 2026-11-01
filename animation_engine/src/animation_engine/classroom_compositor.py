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
    suffix = ""
    while candidate and candidate[-1] in _PUNCTUATION:
        suffix = candidate[-1] + suffix
        candidate = candidate[:-1]
    # Trailing Chinese punctuation is permitted, but Chinese inside an
    # expression must never be silently converted into a fake MathTex glyph.
    if any(ord(c) > 127 for c in candidate):
        raise AdaptiveLayoutError(
            "HEADER_MIXED_SEGMENTS_UNSUPPORTED: supply approved text/math segments"
        )
    if not candidate.strip():
        raise AdaptiveLayoutError("HEADER_EMPTY_MATH")
    try:
        validate_math_latex(candidate)
    except ValueError as exc:
        raise AdaptiveLayoutError(str(exc)) from exc
    if chinese + candidate + suffix != question:
        raise AdaptiveLayoutError("HEADER_SOURCE_CHANGED")
    return chinese, candidate, suffix


def _cjk_font_paths() -> tuple[Path, ...]:
    """Resolve the actual installed CJK font across Linux/Windows/macOS."""
    paths = [Path(path) for path in _CJK_FONT_CANDIDATES]
    windows = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if os.name == "nt" or windows:
        directory = Path(windows or "C:/Windows") / "Fonts"
        paths.extend(directory / name for name in (
            "msyh.ttc", "msyhbd.ttc", "simhei.ttf", "simsun.ttc",
        ))
    paths.extend((
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
    ))
    return tuple(paths)


def _cjk_font_path() -> Path | None:
    return next((p for p in _cjk_font_paths() if p.is_file()), None)


def _cjk_text_font_family() -> str:
    """Use a family actually provided by common Windows system fonts."""
    name = _cjk_font_path()
    if name is None:
        raise AdaptiveLayoutError(
            "CJK_FONT_UNAVAILABLE: install Noto Sans CJK or a CJK system font"
        )
    if name.name.lower().startswith("msyh"):
        return "Microsoft YaHei"
    if name.name.lower().startswith("simhei"):
        return "SimHei"
    if name.name.lower().startswith("simsun"):
        return "SimSun"
    if name.name == "PingFang.ttc":
        return "PingFang SC"
    return "Noto Sans CJK SC"


def _font(size: int):
    from PIL import ImageFont
    for path in _cjk_font_paths():
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    raise AdaptiveLayoutError(
        "CJK_FONT_UNAVAILABLE: install Noto Sans CJK or a CJK system font"
    )


def render_classroom_board_png(
    storyboard, execution, *, event_id: str, output_png: Path, output_json: Path,
    pixel_width: int = 1280, pixel_height: int = 720,
) -> dict:
    """Source-exact mixed Chinese/MathTex header over a verified board."""
    from PIL import Image
    from visual_director.models import StoryboardPlan
    from .header_raster import render_source_header
    from .safe_output import publish_bundle, validate_output_targets

    board = StoryboardPlan.model_validate(storyboard)
    output_png, output_json = Path(output_png), Path(output_json)
    targets = {output_png: ".png", output_json: ".json"}
    validate_output_targets(targets)
    with tempfile.TemporaryDirectory(prefix="classroom-preview-") as temp:
        work = Path(temp)
        old_manifest = render_layout_png(
            board, execution, event_id=event_id,
            output_png=work / "math.png", output_json=work / "math.json",
            pixel_width=pixel_width, pixel_height=pixel_height,
        )
        region = board.scenes[
            next(i for i, scene in enumerate(board.scenes)
                 if scene.event_id == event_id)
        ].regions["question"]
        from .header_raster import source_header_segments
        overlay, header = render_source_header(
            board.header.text,
            pixel_width=pixel_width, pixel_height=pixel_height,
            header_box=(
                region.x * pixel_width, region.y * pixel_height,
                region.w * pixel_width, region.h * pixel_height,
            ),
            font_loader=_font,
            font_size=(31 if pixel_height >= 600 else max(17, pixel_height // 25)),
            math_font_size=34,
            ink_color=board.theme.ink,
            background=board.theme.background,
            align=old_manifest["header"]["align"],
            min_scale=_MIN_HEADER_SCALE, padding=_HEADER_SAFE_PX,
        )
        image = Image.open(work / "math.png").convert("RGBA")
        image.alpha_composite(overlay)
        parts = header["source_segments"]
        math_parts = header["math_segments_latex"]
        preceding = "".join(
            item["value"] for item in parts[:next(
                (i for i, item in enumerate(parts) if item["kind"] == "math"),
                len(parts),
            )] if item["kind"] == "text"
        )
        trailing = parts[-1]["value"] if (
            parts and parts[-1]["kind"] == "text"
            and all(ch in _PUNCTUATION for ch in parts[-1]["value"])
        ) else ""
        manifest = {
            **old_manifest,
            "preview_kind": "real_mathtex_board_and_composed_question_png",
            "header_caption_status": "question_rendered_subtitles_reserved_not_audio_aligned",
            "question_source_sha256": hashlib.sha256(
                board.header.text.encode("utf-8")
            ).hexdigest(),
            "question_parts": {
                "chinese": preceding, "math_latex": (
                    math_parts[0] if len(math_parts) == 1 else None
                ),
                "trailing_punctuation": trailing,
                "source_segments": parts,
            },
            "header_bbox_px": header["header_bbox_px"],
            "header_mathtex_actual_px": header.get("math_bbox_px", [0, 0]),
            "header_display_scale": round(header["scale"], 5),
            "speech_subtitle_status": "not_rendered_no_audio",
        }
        pending_png, pending_json = work / "composed.png", work / "composed.json"
        image.convert("RGB").save(pending_png)
        pending_json.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        publish_bundle({
            output_png: pending_png, output_json: pending_json,
        }, suffixes=targets)
        return manifest
