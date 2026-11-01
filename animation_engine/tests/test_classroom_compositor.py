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


@pytest.mark.render
def test_real_question_mathtex_and_board(tmp_path):
    pytest.importorskip("manim")
    from PIL import Image, ImageChops
    source = Path(__file__).resolve().parents[2] / "visual_director/examples/limit_teaching_package.json"
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
