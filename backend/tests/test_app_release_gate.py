"""Ship both installation apps from exactly one aligned 1.0.1 codebase."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.0.1"


def test_version_metadata_matches_windows_android_and_visible_launcher():
    pkg = json.loads((ROOT / "desktop/package.json").read_text("utf-8"))
    gradle = (ROOT / "android_app/app/build.gradle").read_text("utf-8")
    launcher = (ROOT / "desktop/launcher.html").read_text("utf-8")
    assert pkg["version"] == VERSION
    assert pkg["build"]["productName"] == "微光数学"
    assert "versionCode 2" in gradle
    assert "versionName '1.0.1'" in gradle
    assert "Windows Desktop 1.0.1" in launcher


def test_no_website_substitute_and_no_secrets_bundled():
    pkg = json.loads((ROOT / "desktop/package.json").read_text("utf-8"))
    sources = pkg["build"]["extraResources"]
    for module in ("teacher_module", "visual_director", "animation_engine",
                   "backend", "frontend"):
        bundle = next(e for e in sources
                      if e["to"] == "service/" + module)
        assert all("tests" not in rule for rule in bundle["filter"])
    assert not any(".env" in rule or ".key" in rule for item in sources
                   for rule in item["filter"])
    assert pkg["scripts"]["build:windows"].endswith("--x64")
    app = (ROOT / "android_app/app/src/main/java/cn/weiguang/math/MainActivity.java"
           ).read_text("utf-8")
    assert "UrlPolicy.normalizeServer(raw)" in app
    assert "HttpsURLConnection" in app
    assert "setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW)" in app
    readme = (ROOT / "README.md").read_text("utf-8")
    assert "完全由 WinUI/Kotlin 原生组件重写" in readme
    assert "测试签名" in readme


def test_both_builds_have_handoff_hashes_and_source_provenance():
    windows = (ROOT / ".github/workflows/windows-desktop.yml").read_text("utf-8")
    android = (ROOT / ".github/workflows/android-apk.yml").read_text("utf-8")
    for workflow in (windows, android):
        assert "SHA256SUMS.txt" in workflow
        assert "app-manifest.json" in workflow
        assert "GITHUB_SHA" in workflow
        assert "1.0.1" in workflow
        assert "actions/upload-artifact@v4" in workflow
    assert "setup" in windows.lower() and "portable" in windows.lower()
    assert "testDebugUnitTest lintDebug assembleDebug" in android
    assert "reactivecircus/android-emulator-runner@v2" in android
