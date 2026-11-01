"""Verify classroom preview uses authentic original question without fake subtitles."""
import json
from pathlib import Path
import pytest
from visual_director.director import build_storyboard
from animation_engine.planner import build_execution_plan
from animation_engine.adaptive_layout import AdaptiveLayoutError
from animation_engine.classroom_compositor import _source_parts, render_classroom_board_png


def test_source_preserved():
    orig = "求极限：" + r"\lim_{x\to0}\frac{\sin x}{x}" + "。"
    a, b, c = _source_parts(orig)
    assert a == "求极限："
    assert b == r"\lim_{x\to0}\frac{\sin x}{x}"
    assert c == "。"
    assert a + b + c == orig


def test_mixed_language_refused():
    with pytest.raises(AdaptiveLayoutError, match="HEADER_MIXED_SEGMENTS_UNSUPPORTED"):
        _source_parts(r"\int_0^1 x\,dx请计算")
    with pytest.raises(AdaptiveLayoutError, match="HEADER_SOURCE_EMPTY"):
        _source_parts("")
    with pytest.raises(AdaptiveLayoutError, match="UNSAFE_TEX"):
        _source_parts(r"计算\write18{x}")


def test_mixed_chinese_math_question_keeps_all_source_and_two_mathtex_parts():
    from animation_engine.header_raster import source_header_segments
    question = "若 " + r"\sin x>0" + "，求 " + r"\cos x" + " 的取值范围。"
    parts = source_header_segments(question)
    assert "".join(p["value"] for p in parts) == question
    assert [p["value"] for p in parts if p["kind"] == "math"] == [
        r"\sin x>0", r"\cos x",
    ]
    assert parts[0]["kind"] == "text"
    assert parts[-1]["kind"] == "text"


@pytest.mark.parametrize("question", [
    "计算" + r"\write18{x}" + "的值",
    "求" + r"\frac{x}{2" + "。",
])
def test_mixed_question_does_not_silently_accept_unsafe_math(question):
    from animation_engine.header_raster import source_header_segments
    with pytest.raises(AdaptiveLayoutError, match="UNSAFE_TEX"):
        source_header_segments(question)


def test_mixed_source_includes_plain_ascii_variables_and_values():
    from animation_engine.header_raster import source_header_segments
    question = "已知 x>0，求 y^2+1 的范围。"
    segments = source_header_segments(question)
    assert [s["value"] for s in segments if s["kind"] == "math"] == [
        "x>0", "y^2+1",
    ]
    assert "".join(s["value"] for s in segments) == question


@pytest.mark.render
def test_real_question_mathtex_and_board(tmp_path):
    pytest.importorskip("manim")
    from PIL import Image, ImageChops
    source = Path(__file__).resolve().parents[2] / "visual_director/tests/fixtures/limit_teaching_package.json"
    board = build_storyboard(json.loads(source.read_text(encoding="utf-8")))
    execution = build_execution_plan(board)
    image = tmp_path / "classroom.png"
    manifest = tmp_path / "classroom.json"
    result = render_classroom_board_png(board, execution,
        event_id="e_k_eqv", output_png=image, output_json=manifest)
    assert result["preview_kind"] == "real_mathtex_board_and_composed_question_png"
    assert result["speech_subtitle_status"] == "not_rendered_no_audio"
    assert result["question_parts"]["chinese"] == "求极限："
    assert result["question_parts"]["math_latex"].startswith(r"\lim")
    assert result["header_display_scale"] >= .9
    with Image.open(image) as picture:
        upper = picture.convert("RGB").crop((0, 0, 1280, 125))
        blank = Image.new("RGB", upper.size, "white")
        assert ImageChops.difference(upper, blank).getbbox() is not None
    assert json.loads(manifest.read_text(encoding="utf-8"))["preview_event_id"] == "e_k_eqv"
