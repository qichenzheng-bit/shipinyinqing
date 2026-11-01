"""No-render path safety, Windows-friendly FFconcat and output rollback."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from animation_engine import safe_output
from animation_engine.safe_output import (
    OutputSafetyError, course_source_files, ffconcat_file,
    publish_bundle, validate_output_targets,
)
from animation_engine.spoken_movie import render_spoken_classroom


def test_mp4_json_srt_collisions_are_rejected_before_tts(tmp_path, monkeypatch):
    course = tmp_path / "course"
    course.mkdir()
    source = course / "spoken_classroom.json"
    source.write_text('{"source":"never-render"}', encoding="utf-8")
    movie = tmp_path / "movie.mp4"
    manifest = tmp_path / "manifest.json"
    # The output argument is invalid before source parsing/TTS/Manim.
    with pytest.raises(OutputSafetyError, match="OUTPUT_INVALID_TARGET"):
        render_spoken_classroom(
            source, output_mp4=movie, output_json=manifest,
            output_srt=movie, adaptive=False,
        )
    with pytest.raises(OutputSafetyError, match="OUTPUT_INVALID_TARGET"):
        render_spoken_classroom(
            source, output_mp4=movie,
            output_json=source, output_srt=movie.with_suffix(".srt"),
            adaptive=False,
        )
    with pytest.raises(OutputSafetyError, match="OUTPUT_TARGET_COLLISION"):
        validate_output_targets({
            tmp_path / "same.json": ".json",
            tmp_path / "other.json": ".json",
        }, protected=[tmp_path / "same.json"])


def test_prevent_overwriting_package_source_manifest(tmp_path):
    source = tmp_path / "lesson" / "spoken_classroom.json"
    source.parent.mkdir()
    source.write_text('{"teacher_reviewed":true}')
    stage = source.parent / "stage"
    stage.mkdir()
    (stage / "storyboard.json").write_text("{}")
    allowed = source.parent / "manifest.json"
    assert source in course_source_files(source)
    assert stage / "storyboard.json" in course_source_files(source)
    validate_output_targets({allowed: ".json"}, protected=course_source_files(source))
    with pytest.raises(OutputSafetyError, match="OUTPUT_OVERWRITES_SOURCE"):
        validate_output_targets({stage / "storyboard.json": ".json"},
                                protected=course_source_files(source))


def test_bundle_preserves_successful_video_when_second_publish_fails(
        tmp_path, monkeypatch):
    movie, manifest = tmp_path / "result.mp4", tmp_path / "result.json"
    movie.write_bytes(b"older-verified-movie")
    manifest.write_bytes(b'{"older":true}')
    new_movie = tmp_path / "new-media.mp4"
    new_movie.write_bytes(b"new-movie")
    original_replace = safe_output.os.replace

    def fail_second(source, destination):
        if (Path(destination) == manifest
                and Path(source).name.startswith(".pending-")):
            raise OSError("simulated second replace failure")
        return original_replace(source, destination)

    monkeypatch.setattr(safe_output.os, "replace", fail_second)
    with pytest.raises(OSError, match="simulated"):
        publish_bundle({
            movie: new_movie,
            manifest: b'{"new":true}',
        }, suffixes={movie: ".mp4", manifest: ".json"})
    assert movie.read_bytes() == b"older-verified-movie"
    assert json.loads(manifest.read_text()) == {"older": True}
    assert not list(tmp_path.glob(".pending-*"))
    assert not list(tmp_path.glob(".prior-*"))


def test_bundle_invalid_paths_leave_old_artifacts_intact(tmp_path):
    movie = tmp_path / "result.mp4"
    old = b"old-video"
    movie.write_bytes(old)
    with pytest.raises(OutputSafetyError, match="OUTPUT_INVALID_TARGET"):
        publish_bundle({
            movie: b"new-video",
            tmp_path / "result.json": b"not-json",
        }, suffixes={movie: ".mp4", tmp_path / "result.json": ".srt"})
    assert movie.read_bytes() == old


def test_ffconcat_escapes_apostrophe_and_rejects_newlines(tmp_path):
    name = tmp_path / "teacher's lessons" / "unit 1.mp4"
    actual = ffconcat_file(name)
    assert actual.startswith("file '")
    assert actual.endswith("'\n")
    assert r"'\''" in actual
    assert "teacher" in actual and "unit 1.mp4" in actual
    with pytest.raises(OutputSafetyError, match="FFCONCAT_INVALID_PATH"):
        ffconcat_file(Path("bad\nname.mp4"))
