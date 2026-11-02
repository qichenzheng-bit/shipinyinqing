"""Strict and read-only release inventory for the WeiGuang Math repository.

No tests, fixture prompts, source packages, media data, or encrypted model
configuration are ever deleted by an inventory check.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROJECTS=("teacher_module","visual_director","animation_engine","backend")
PROMPTS={
    "teacher_module/src/math_teacher/prompts/global.md",
    "teacher_module/src/math_teacher/prompts/a_understanding.md",
    "teacher_module/src/math_teacher/prompts/b_planning.md",
    "teacher_module/src/math_teacher/prompts/c_narration.md",
}
CRITICAL={
    ".github/workflows/system-ci.yml",
    ".github/workflows/windows-desktop.yml",
    ".github/workflows/frontend-screenshots.yml",
    ".github/workflows/final-new-question.yml",
    "docker-compose.yml",
    "backend/src/weiguang_backend/main.py",
    "backend/src/weiguang_backend/model_hub.py",
    "frontend/app.js",
    "frontend/logo.svg",
    "desktop/main.cjs",
    "desktop/preload.cjs",
    "desktop/package.json",
    "desktop/tools/generate_app_icon.py",
    "animation_engine/src/animation_engine/spoken_movie.py",
    "animation_engine/src/animation_engine/brand_watermark.py",
    "visual_director/src/visual_director/director.py",
    "README.md",
} | PROMPTS


def tracked_files():
    result=subprocess.run(
        ["git","ls-files","-z"],cwd=ROOT,capture_output=True,check=True,
    )
    return {
        Path(piece.decode("utf-8")).as_posix()
        for piece in result.stdout.split(b"\0") if piece
    }


def main():
    files=tracked_files()
    missing=CRITICAL-files
    obsolete=sorted(name for name in files if name.startswith("android_app/")
                    or name in (".github/workflows/android-apk.yml",
                                "backend/tests/capture_android_mobile.py",
                                "backend/tests/test_android_delivery.py"))
    if obsolete:
        raise AssertionError("ANDROID_FILES_REMAIN_AFTER_WINDOWS_ONLY_RELEASE: "+str(obsolete))
    if missing:raise AssertionError("MISSING_PRODUCTION_RESOURCES: "+str(sorted(missing)))
    markdowns={name for name in files if name.endswith(".md")}
    if markdowns!=PROMPTS|{"README.md"}:
        raise AssertionError("REDUNDANT_OR_MISSING_MARKDOWN: "+str(sorted(markdowns)))
    forbidden=[
        name for name in files
        if (name==".env" or name.endswith((".log",".mp4",".mov",".wav",".mp3",".srt",".zip",
                               ".exe",".msi",".apk",".aab",".pem",".key",".ico"))
            or "node_modules/" in name or "/__pycache__/" in name
            or name.startswith((".weiguang_data/","desktop/dist/","desktop/build/",
                                 "frontend/screenshots/","desktop/screenshots/",
                                 "final-output/","v27-script/"))
            or name.startswith("config/edit_ai.json")
            or name in ("animation_engine/examples/simple_classroom_policy.template.json",
                        "animation_engine/examples/longboard_policy.template.json"))
    ]
    if forbidden:
        raise AssertionError("GENERATED_OR_PRIVATE_FILES_TRACKED: "+str(forbidden))
    for module in PROJECTS:
        if not any(name.startswith(module+"/src/") for name in files):
            raise AssertionError("MISSING_MODULE_SOURCE: "+module)
    manifest=json.loads((ROOT/"desktop/package.json").read_text(encoding="utf-8"))
    shipped=manifest["build"]["extraResources"]
    for module in PROJECTS:
        entry=next((item for item in shipped if item["to"]=="service/"+module),None)
        if entry is None or not any(pattern=="src/**/*" for pattern in entry["filter"]):
            raise AssertionError("DESKTOP_MODULE_NOT_PACKAGED: "+module)
        if any("tests" in item for item in entry["filter"]):
            raise AssertionError("TESTS_SHIPPED_IN_INSTALLER: "+module)
    assert all((ROOT/path).is_file() for path in PROMPTS)
    print("REPOSITORY_RELEASE_AUDIT_OK",
          len(files),"tracked files",
          len(markdowns),"runtime markdown resources")


if __name__=="__main__":
    main()
