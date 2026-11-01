"""Regression protection for V2.6 audit fixes; no mocked real-video claims."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from animation_engine import iterative_edit_engine as editing
from animation_engine.classroom_cues import NOTE_CHARACTERS
from animation_engine.iterative_ai_adapter import _RejectCredentialRedirects


def _version_files(folder: Path, prefix: bytes):
    folder.mkdir(parents=True, exist_ok=True)
    for filename in ("movie.mp4", "movie_manifest.json", "captions.srt"):
        (folder / filename).write_bytes(prefix + b":" + filename.encode())


def _latest_files(folder: Path, prefix: bytes):
    for filename in ("latest.mp4", "latest_manifest.json", "latest.srt"):
        (folder / filename).write_bytes(prefix + b":" + filename.encode())


def test_bundle_publish_exception_rolls_back_all_three_aliases(tmp_path, monkeypatch):
    source = tmp_path / "versions" / "0001"
    _version_files(source, b"new")
    _latest_files(tmp_path, b"old")
    original = editing._publish
    tripped = [False]

    def fail_once(src, target):
        if Path(target).name == "latest_manifest.json" and not tripped[0]:
            tripped[0] = True
            raise OSError("simulated interrupted write")
        return original(src, target)

    monkeypatch.setattr(editing, "_publish", fail_once)
    with pytest.raises(OSError, match="simulated"):
        editing._publish_bundle(source, tmp_path)
    assert (tmp_path / "latest.mp4").read_bytes() == b"old:latest.mp4"
    assert (tmp_path / "latest_manifest.json").read_bytes() == b"old:latest_manifest.json"
    assert (tmp_path / "latest.srt").read_bytes() == b"old:latest.srt"


def test_crash_left_mixed_aliases_are_recovered_from_committed_revision(tmp_path):
    version = tmp_path / "versions" / "0001"
    _version_files(version, b"immutable")
    _latest_files(tmp_path, b"stale")
    state = {
        "schema_version": "1.0",
        "mode": "iterative_video_edit",
        "revision": 1,
    }
    (tmp_path / "edit_session.json").write_text(json.dumps(state))
    assert editing._state(tmp_path)["revision"] == 1
    assert (tmp_path / "latest.mp4").read_bytes() == (version / "movie.mp4").read_bytes()
    assert (tmp_path / "latest_manifest.json").read_bytes() == (version / "movie_manifest.json").read_bytes()
    assert (tmp_path / "latest.srt").read_bytes() == (version / "captions.srt").read_bytes()


def test_provider_redirect_handler_does_not_create_authorized_redirect():
    reject = _RejectCredentialRedirects()
    assert reject.redirect_request(None, None, 302, "Moved", {}, "https://unsafe.invalid/") is None


def test_numbered_chinese_board_notes_remain_source_text_not_phonetic_math():
    assert NOTE_CHARACTERS.fullmatch("第1步，先观察题目。")
    assert not NOTE_CHARACTERS.fullmatch("令x=1后继续。")
