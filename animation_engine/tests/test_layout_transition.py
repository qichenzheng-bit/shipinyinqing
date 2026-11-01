"""2.3 transition truthfulness and real mp4 (render-marked) tests."""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from animation_engine.adaptive_layout import AdaptiveLayoutError, _overlap, layout_storyboard, GlyphSize
from animation_engine.layout_transition import _verify_moving_bounds, render_layout_transition
from animation_engine.planner import build_execution_plan
from visual_director.director import build_storyboard


@pytest.fixture(scope="module")
def approved():
    file = (Path(__file__).resolve().parents[2] /
            "visual_director/examples/limit_teaching_package.json")
    board = build_storyboard(json.loads(file.read_text(encoding="utf-8")))
    return board, build_execution_plan(board)


def test_tween_collision_rejected():
    before = {"a": {"x": 10, "y": 10, "w": 30, "h": 15},
              "b": {"x": 80, "y": 10, "w": 30, "h": 15}}
    after = {"a": {"x": 80, "y": 10, "w": 30, "h": 15},
             "b": {"x": 10, "y": 10, "w": 30, "h": 15}}
    with pytest.raises(AdaptiveLayoutError, match="TRANSITION_COLLISION"):
        _verify_moving_bounds(before, after)


def test_tween_nonoverlap_passes():
    before = {"a": {"x": 10, "y": 10, "w": 30, "h": 15},
              "b": {"x": 10, "y": 55, "w": 30, "h": 15}}
    after = {"a": {"x": 15, "y": 10, "w": 30, "h": 15},
             "b": {"x": 15, "y": 55, "w": 30, "h": 15}}
    _verify_moving_bounds(before, after)


def test_nonconsecutive_transition_refused_prior_to_render(approved, tmp_path):
    board, plan = approved
    events = [s.event_id for s in board.scenes]
    with pytest.raises(AdaptiveLayoutError, match="NONCONSECUTIVE_EVENTS"):
        render_layout_transition(board, plan, from_event_id=events[0],
                                 to_event_id=events[-1],
                                 output_mp4=tmp_path/"bad.mp4",
                                 output_json=tmp_path/"bad.json")
    assert not list(tmp_path.iterdir())


@pytest.mark.render
def test_real_two_scene_transition_mp4(approved, tmp_path):
    pytest.importorskip("manim")
    board, plan = approved
    layout = layout_storyboard(board, plan)
    pair = next((
        (a, b) for a, b in zip(layout["scenes"], layout["scenes"][1:])
        if a["status"] == b["status"] == "ready" and b["placements"]
    ), None)
    assert pair is not None
    movie, manifest = tmp_path/"move.mp4", tmp_path/"move.json"
    rendered = render_layout_transition(
        board, plan, from_event_id=pair[0]["event_id"],
        to_event_id=pair[1]["event_id"],
        output_mp4=movie, output_json=manifest)
    assert movie.stat().st_size > 1000
    assert rendered["render_kind"] == "manim_mathtex_two_scene_layout_transition_mp4"
    assert rendered["timing_source"] == "preview_only_not_audio_aligned"
    assert rendered["source_storyboard_sha256"] == plan.source_storyboard_sha256
    assert set(rendered["moved_ids"] + rendered["held_ids"] +
               rendered["written_ids"]) == {
                   p["object_id"] for p in pair[1]["placements"]
               }
    assert json.loads(manifest.read_text(encoding="utf-8")) == rendered
