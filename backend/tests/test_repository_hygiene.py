"""Clean repository sources without discarding video records or review fixtures."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def tracked():
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT,
        check=True, capture_output=True,
    )
    return {p.decode("utf-8") for p in result.stdout.split(b"\0") if p}


def get_cleanup_module():
    path = ROOT / "tools" / "clean_generated.py"
    spec = importlib.util.spec_from_file_location("weiguang_safe_cleanup", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_release_tree_contains_only_required_source_not_generated_evidence():
    files = tracked()
    assert not any(p.startswith(("frontend/screenshots/", "desktop/screenshots/",
                                 "final-output/", "v27-script/", "android_app/"))
                   for p in files)
    assert not any(p.startswith("animation_engine/examples/") for p in files)
    assert not any(p.startswith("deploy/") for p in files)
    assert "animation_engine/src/animation_engine/recap_board.py" in files
    assert "desktop/package.json" in files
    assert "backend/src/weiguang_backend/main.py" in files
    assert ".github/workflows/windows-desktop.yml" in files
    assert ".github/workflows/final-new-question.yml" in files
    assert "animation_engine/tests/fixtures/build_final_fresh_trig_limit.py" in files
    assert (ROOT / "frontend" / "app.js").is_file()


def test_generated_file_guards_block_future_accidental_commits():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("frontend/screenshots/", "desktop/screenshots/",
                    "final-output/", "v27-script/", "*.mp4", "*.exe"):
        assert pattern in ignore, pattern
    audit = (ROOT / "tools" / "repository_audit.py").read_text(encoding="utf-8")
    assert "frontend/screenshots/" in audit
    assert "desktop/screenshots/" in audit
    assert "MISSING_PRODUCTION_RESOURCES" in audit

    for path in ("system-ci.yml", "frontend-screenshots.yml", "windows-desktop.yml"):
        workflow=(ROOT / ".github/workflows" / path).read_text(encoding="utf-8")
        assert "runs-on: ubuntu" not in workflow, path
        assert "windows-latest" in workflow, path
    assert "runs-on: ubuntu-latest" in (
        ROOT / ".github/workflows/final-new-question.yml"
    ).read_text(encoding="utf-8")  # Docker-compatible MEDIA CI, not Linux app


def test_cleanup_dry_run_and_apply_remove_only_reproducible_builds(tmp_path, capsys):
    mod = get_cleanup_module()
    mod.ROOT = tmp_path
    screenshot = tmp_path / "frontend" / "screenshots" / "01-demo.png"
    screenshot.parent.mkdir(parents=True)
    screenshot.write_bytes(b"rebuildable-test-image")
    user_video = tmp_path / ".weiguang_data" / "videos" / "lesson.mp4"
    user_video.parent.mkdir(parents=True)
    user_video.write_bytes(b"permanent-user-video")
    real_key = tmp_path / ".env"
    real_key.write_text("PRIVATE=DO_NOT_DELETE", encoding="utf-8")
    original = screenshot.read_bytes()
    mod.clean(apply=False)
    assert screenshot.read_bytes() == original
    assert user_video.is_file()
    assert real_key.is_file()
    mod.clean(apply=True)
    assert not screenshot.exists()
    assert user_video.read_bytes() == b"permanent-user-video"
    assert real_key.read_text(encoding="utf-8") == "PRIVATE=DO_NOT_DELETE"


def test_cleanup_refuses_symlinked_generated_directories(tmp_path):
    mod = get_cleanup_module()
    mod.ROOT = tmp_path
    forbidden = tmp_path / "user_data"
    forbidden.mkdir()
    link = tmp_path / "frontend" / "screenshots"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(forbidden, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Platform does not allow this symlink")
    with pytest.raises(RuntimeError, match="UNSAFE_GENERATED_PATH"):
        mod.clean(apply=True)
    assert forbidden.exists()
