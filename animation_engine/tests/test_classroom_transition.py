"""Actual classroom video retains authentic question across moving MathTex."""
import json
from pathlib import Path
import pytest
from visual_director.director import build_storyboard
from animation_engine.planner import build_execution_plan
from animation_engine.classroom_transition import render_classroom_transition
from animation_engine.adaptive_layout import AdaptiveLayoutError


@pytest.mark.render
def test_genuine_classroom_video_with_fixed_question(tmp_path):
    pytest.importorskip("manim")
    source=Path(__file__).resolve().parents[2] / "visual_director/tests/fixtures/limit_teaching_package.json"
    board=build_storyboard(json.loads(source.read_text(encoding="utf-8")))
    plan=build_execution_plan(board)
    video=tmp_path/"classroom.mp4"
    manifest=tmp_path/"classroom.json"
    result=render_classroom_transition(board,plan,
        from_event_id="e_common",to_event_id="e_k_eqv",
        output_mp4=video,output_json=manifest,fps=30)
    assert video.stat().st_size>1000
    assert result["fps"]==30
    assert result["held_ids"] and result["written_ids"]
    assert result["question_parts"]["chinese"] == "求极限："
    assert result["question_parts"]["math_latex"].startswith(r"\lim")
    assert result["subtitle_status"]=="not_rendered_no_audio"
    assert result["timing_source"]=="preview_only_not_audio_aligned"
    assert json.loads(manifest.read_text(encoding="utf-8"))==result

"""Basic safety checks without requiring a media environment."""
from pathlib import Path
import pytest
from animation_engine.classroom_transition import render_classroom_transition
from animation_engine.adaptive_layout import AdaptiveLayoutError


def test_refuse_overlapping_paths_before_render(tmp_path):
    path=tmp_path/"same.mp4"
    with pytest.raises(AdaptiveLayoutError,match="INVALID_OUTPUT"):
        render_classroom_transition({}, {}, from_event_id="a", to_event_id="b",
            output_mp4=path, output_json=path)
