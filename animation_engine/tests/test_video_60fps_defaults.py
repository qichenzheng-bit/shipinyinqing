"""Video production defaults at 60 FPS, without rendering a single frame."""
from __future__ import annotations

import importlib
import inspect

import pytest

from animation_engine.video_settings import (
    DEFAULT_VIDEO_FPS, BOARD_WIPE_SECONDS, transition_frame_count,
)


@pytest.mark.parametrize("module,function", [
    ("animation_engine.spoken_movie", "render_spoken_classroom"),
    ("animation_engine.unified_classroom_flow", "render_flow"),
    ("animation_engine.adaptive_classroom_flow", "render_adaptive_flow"),
    ("animation_engine.classroom_math_memory", "render_memory"),
    ("animation_engine.iterative_edit_engine", "create_session"),
    ("animation_engine.persistent_chalkboard", "render_persistent_chalkboard"),
    ("animation_engine.longboard_render", "render_longboard_movie"),
    ("animation_engine.classroom_sequence", "render_classroom_sequence"),
    ("animation_engine.classroom_transition", "render_classroom_transition"),
    ("animation_engine.layout_transition", "render_layout_transition"),
    ("animation_engine.writing_clip", "render_math_writing_clip"),
])
def test_every_video_production_entrypoint_uses_60fps_by_default(module, function):
    target = getattr(importlib.import_module(module), function)
    assert inspect.signature(target).parameters["fps"].default == DEFAULT_VIDEO_FPS == 60


def test_board_wipe_preserves_duration_across_frame_rates():
    assert BOARD_WIPE_SECONDS == 0.6
    assert transition_frame_count(60) == 36
    assert transition_frame_count(30) == 18
    assert transition_frame_count(15) == 9
    assert transition_frame_count(36) / 60 == transition_frame_count(18) / 30
    for invalid in (0, 61, True, 60.0, "60"):
        with pytest.raises(ValueError, match="VIDEO_FPS_OUT_OF_RANGE"):
            transition_frame_count(invalid)


def test_cli_spoken_render_uses_60fps_without_producing_a_movie(monkeypatch, tmp_path):
    from animation_engine.cli import main
    from animation_engine import spoken_movie

    recorded = {}

    def fake_renderer(*args, **kwargs):
        recorded.update(kwargs)
        recorded["called"] = True

    monkeypatch.setattr(spoken_movie, "render_spoken_classroom", fake_renderer)
    assert main([
        "render-spoken", "--spoken", str(tmp_path / "lesson.json"),
        "--output", str(tmp_path / "lesson.mp4"),
        "--manifest", str(tmp_path / "manifest.json"),
    ]) == 0
    assert recorded["called"]
    assert recorded["fps"] == 60
    assert not (tmp_path / "lesson.mp4").exists()


def test_cli_explicit_legacy_fps_override_remains_available(monkeypatch, tmp_path):
    from animation_engine.cli import main
    from animation_engine import spoken_movie

    seen = []
    monkeypatch.setattr(
        spoken_movie, "render_spoken_classroom",
        lambda *a, **k: seen.append(k["fps"]),
    )
    assert main([
        "render-spoken", "--spoken", str(tmp_path / "lesson.json"),
        "--output", str(tmp_path / "lesson.mp4"),
        "--manifest", str(tmp_path / "manifest.json"),
        "--fps", "30",
    ]) == 0
    assert seen == [30]
    assert not (tmp_path / "lesson.mp4").exists()
