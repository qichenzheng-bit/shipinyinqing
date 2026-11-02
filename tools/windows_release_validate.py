"""Read-only Windows-only release checks plus deterministic non-render lesson fixture.

The only output is disposable v27-script/ (ignored), not a user data folder.
Never installs OS packages, edits backend state or deletes real video files.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from animation_engine.video_settings import DEFAULT_VIDEO_FPS, transition_frame_count

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = {
    "teacher_module/src/math_teacher/prompts/global.md",
    "teacher_module/src/math_teacher/prompts/a_understanding.md",
    "teacher_module/src/math_teacher/prompts/b_planning.md",
    "teacher_module/src/math_teacher/prompts/c_narration.md",
}


def check_documentation() -> None:
    sources = {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*.md")
        if not any(part.startswith(".") or part in {
            "__pycache__", "node_modules", "dist", "build", "v27-script"
        } for part in path.relative_to(ROOT).parts)
    }
    assert sources == PROMPTS | {"README.md"}, sources
    assert all((ROOT / p).stat().st_size > 100 for p in PROMPTS)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Windows 单平台" in readme
    assert "Docker Desktop" in readme
    assert "WSL2" in readme
    assert "归纳总结" in readme
    assert not (ROOT / "android_app").exists()
    assert not (ROOT / "deploy").exists()


def check_lesson_without_media() -> None:
    output = ROOT / "v27-script"
    subprocess.run([
        sys.executable,
        "animation_engine/tests/fixtures/build_novel_substitution_integral.py",
        "--output", str(output),
    ], cwd=ROOT, check=True)
    subprocess.run([
        "math-animation", "export-spoken-script",
        "--spoken", str(output / "spoken_classroom.json"),
        "--output", str(output / "lesson_script.md"),
    ], cwd=ROOT, check=True)
    result = json.loads((output / "lesson_script.json").read_text("utf-8"))
    assert result["acceptance"]["contract_version"] == "2.7"
    assert result["events"][0]["phase"] == "observe"
    assert result["events"][-1]["phase"] == "summary"
    assert DEFAULT_VIDEO_FPS == 60
    assert transition_frame_count(60) == 36
    narration = (output / "lesson_script.md").read_text("utf-8")
    assert "我们来读一下这道题" not in narration
    assert not list(output.rglob("*.mp4"))
    print("WINDOWS_V27_NON_RENDER_APPROVED", len(result["events"]), "events")


if __name__ == "__main__":
    check_documentation()
    check_lesson_without_media()
    print("WINDOWS_ONLY_SOURCE_AND_DOCS_ACCEPTED")
