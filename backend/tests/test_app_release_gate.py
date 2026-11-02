"""Windows-only app release checks: no Android code, no accidental user-data removal."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.0.2"


def test_windows_setup_portable_versions_and_app_launcher():
    pkg = json.loads((ROOT / "desktop/package.json").read_text("utf-8"))
    launcher = (ROOT / "desktop/launcher.html").read_text("utf-8")
    assert pkg["version"] == VERSION
    assert pkg["productName"] == "微光数学"
    assert pkg["build"]["appId"] == "cn.weiguang.math"
    assert "Windows Desktop 1.0.2" in launcher
    assert pkg["scripts"]["build:windows"].endswith("--x64")
    assert pkg["build"]["nsis"]["createDesktopShortcut"]
    assert "nsis" in str(pkg["build"]["win"]["target"])
    assert "portable" in str(pkg["build"]["win"]["target"])


def test_only_required_runtime_modules_shipped_without_source_tests_or_keys():
    pkg = json.loads((ROOT / "desktop/package.json").read_text("utf-8"))
    sources = pkg["build"]["extraResources"]
    for module in ("teacher_module", "visual_director", "animation_engine",
                   "backend", "frontend"):
        bundle = next(e for e in sources if e["to"] == "service/" + module)
        assert all("tests" not in pattern for pattern in bundle["filter"])
    assert not any(".env" in pattern or ".key" in pattern
                   for e in sources for pattern in e["filter"])
    assert (ROOT / "animation_engine/src/animation_engine/recap_board.py").is_file()


def test_removed_mobile_app_no_longer_in_release_pipeline():
    assert not (ROOT / "android_app").exists()
    assert not (ROOT / ".github/workflows/android-apk.yml").exists()
    assert not (ROOT / "backend/tests/capture_android_mobile.py").exists()
    assert not (ROOT / "backend/tests/test_android_delivery.py").exists()
    readme=(ROOT / "README.md").read_text(encoding="utf-8")
    assert "Windows 单平台" in readme
    assert "Windows Setup" in readme


def test_windows_build_handoff_has_checksums_provenance_and_native_smoke():
    workflow=(ROOT / ".github/workflows/windows-desktop.yml").read_text("utf-8")
    assert "SHA256SUMS.txt" in workflow
    assert "app-manifest.json" in workflow
    assert "GITHUB_SHA" in workflow
    assert "1.0.2" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "npm run test:native" in workflow
    assert "WINDOWS_NATIVE_INSTALLER_ACCEPTANCE_OK" in workflow
