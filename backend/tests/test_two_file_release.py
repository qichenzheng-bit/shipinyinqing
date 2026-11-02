"""Final two-file release must contain executable and audited source, no generated media."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.0.4"


def builder():
    path = ROOT / "tools" / "build_source_release.py"
    spec = importlib.util.spec_from_file_location("weiguang_source_release", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_maintenance_zip_has_real_source_and_regression_tests_but_no_media():
    tool = builder()
    paths = tool.source_file_inventory()
    assert all(tool.is_source_file(p) for p in paths)
    assert "README.md" in paths
    assert "docker-compose.yml" in paths
    assert "backend/src/weiguang_backend/database.py" in paths
    assert "animation_engine/src/animation_engine/recap_board.py" in paths
    assert "animation_engine/tests/test_global_recap_board.py" in paths
    assert "teacher_module/src/math_teacher/prompts/global.md" in paths
    assert "visual_director/tests/fixtures/limit_teaching_package.json" in paths
    for suffix in (".mp4", ".wav", ".exe", ".db", ".png", ".zip"):
        assert not [p for p in paths if p.lower().endswith(suffix)]


def test_zip_builder_binds_source_to_exact_installer_without_temp_data(tmp_path):
    tool = builder()
    installer = tmp_path / "WeiGuang-Math-Setup-1.0.4-x64.exe"
    installer.write_bytes(b"RELEASE_FIXTURE_NOT_A_REAL_INSTALLER" + b"X" * 25_000_000)
    archive_path = tmp_path / "WeiGuang-Math-Source-1.0.4.zip"
    report = tool.build_release(
        setup=installer, output=archive_path,
        version=VERSION, source_sha="a" * 40,
    )
    assert report["installer"] == installer.name
    assert report["installer_sha256"] == tool.sha256(installer)
    assert report["database"] == "PostgreSQL 17 only"
    assert report["source_file_count"] >= 100
    with ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert all(n.startswith("WeiGuang-Math-Source-1.0.4/") for n in names)
        assert not any(n.lower().endswith((".exe", ".mp4", ".png", ".db"))
                       for n in names)
        manifest = json.loads(archive.read(
            "WeiGuang-Math-Source-1.0.4/release-manifest.json"
        ))
        assert manifest["installer_sha256"] == report["installer_sha256"]
        assert len(manifest["source_file_sha256"]) == report["source_file_count"]


def test_portable_removed_from_build_and_release_workflow():
    package = json.loads((ROOT / "desktop/package.json").read_text("utf-8"))
    assert package["version"] == VERSION
    assert package["scripts"]["build:windows"] == "electron-builder --win nsis --x64"
    assert len(package["build"]["win"]["target"]) == 1
    assert package["build"]["win"]["target"][0]["target"] == "nsis"
    assert "portable" not in package["build"]
    workflow = (ROOT / ".github/workflows/windows-desktop.yml").read_text("utf-8")
    assert "WeiGuang-Math-Setup-1.0.4-x64.exe" in workflow
    assert "WeiGuang-Math-Source-1.0.4.zip" in workflow
    assert "EXACTLY_TWO_WINDOWS_RELEASE_FILES_ACCEPTED" in workflow
    assert "desktop/dist/*.exe" in workflow  # strict file-count assertion, not upload
    assert "name: WeiGuang-Math-Windows-v1.0.4-Installer-and-Source" in workflow
    assert "WeiGuang-Math-Portable-1.0.4" not in workflow
