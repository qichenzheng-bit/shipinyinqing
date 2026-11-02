"""Build the single maintainable source ZIP for the Windows-only release.

Only tracked, source-controlled files enter the archive: no generated movies,
images, screenshots, database files, local keys, Docker volumes or build caches.
Retain the deterministic regression-test code/fixtures needed for upgrades.
The second and ONLY other release asset is the checked Windows Setup EXE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PREFIXES = (
    ".git/", "data/", ".weiguang_data/", "desktop/dist/", "desktop/build/",
    "desktop/screenshots/", "frontend/screenshots/", "final-output/",
    "v27-script/", "android_app/", "deploy/", "linux/",
)
PRIVATE_NAMES = {".env", "config/edit_ai.json", "launcher.json", "local-secrets.bin"}
BINARY_SUFFIXES = {
    ".mp4", ".mov", ".mkv", ".webm", ".wav", ".mp3", ".flac", ".srt",
    ".exe", ".msi", ".apk", ".aab", ".appimage", ".deb", ".rpm", ".snap",
    ".db", ".sqlite", ".sqlite3", ".db-wal", ".db-journal", ".db-shm",
    ".pem", ".key", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".zip", ".7z", ".tar", ".gz", ".log", ".pyc", ".pyo",
}
RUNTIME_FILES = {
    "README.md", "docker-compose.yml", "backend/Dockerfile",
    "desktop/package.json", "desktop/main.cjs", "desktop/preload.cjs",
    "desktop/cli_bridge.cjs", "backend/src/weiguang_backend/cli_bridge.py",
    "backend/src/weiguang_backend/main.py",
    "backend/src/weiguang_backend/database.py",
    "animation_engine/src/animation_engine/recap_board.py",
    "teacher_module/src/math_teacher/prompts/global.md",
    "visual_director/src/visual_director/director.py",
    "frontend/app.js", "frontend/logo.svg",
    "tools/build_source_release.py",
}
MAINTENANCE_FILES = {
    ".github/workflows/system-ci.yml",
    ".github/workflows/windows-desktop.yml",
    "backend/tests/test_postgresql_only.py",
    "backend/tests/test_global_cli_model.py", "desktop/tests/cli_bridge.test.cjs",
    "animation_engine/tests/test_global_recap_board.py",
}


def tracked_files(root: Path = ROOT) -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root,
        check=True, capture_output=True,
    )
    return sorted(p.decode("utf-8") for p in proc.stdout.split(b"\0") if p)


def is_source_file(name: str) -> bool:
    path = Path(name)
    return (
        bool(name)
        and not name.startswith(EXCLUDED_PREFIXES)
        and name not in PRIVATE_NAMES
        and not any(part in {"node_modules", "__pycache__", ".pytest_cache", ".git"}
                    for part in path.parts)
        and not name.endswith((".egg-info/PKG-INFO",))
        and path.suffix.lower() not in BINARY_SUFFIXES
        and not path.is_absolute()
        and ".." not in path.parts
    )


def source_file_inventory(root: Path = ROOT) -> list[str]:
    files = [p for p in tracked_files(root) if is_source_file(p)]
    if len(files) != len(set(files)):
        raise RuntimeError("SOURCE_RELEASE_DUPLICATED_PATH")
    missing = sorted((RUNTIME_FILES | MAINTENANCE_FILES) - set(files))
    if missing:
        raise RuntimeError("SOURCE_RELEASE_REQUIRED_FILES_MISSING: " + str(missing))
    for path in files:
        if not (root / path).is_file():
            raise RuntimeError("SOURCE_RELEASE_TRACKED_FILE_MISSING: " + path)
    if not any(p.startswith("animation_engine/tests/fixtures/") for p in files):
        raise RuntimeError("SOURCE_RELEASE_REGRESSION_TEST_FIXTURES_MISSING")
    return files


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_release(*, setup: Path, output: Path, version: str, source_sha: str,
                  root: Path = ROOT) -> dict:
    if not setup.is_file() or setup.stat().st_size < 25_000_000:
        raise RuntimeError("SOURCE_RELEASE_VALID_WINDOWS_SETUP_REQUIRED")
    if setup.name != f"WeiGuang-Math-Setup-{version}-x64.exe":
        raise RuntimeError("SOURCE_RELEASE_SETUP_VERSION_MISMATCH")
    if not source_sha or len(source_sha) != 40:
        raise RuntimeError("SOURCE_RELEASE_GIT_SHA_REQUIRED")
    manifest = {
        "product": "微光数学",
        "platform": "Windows x64 only",
        "version": version,
        "git_commit": source_sha,
        "database": "PostgreSQL 17 only",
        "installer": setup.name,
        "installer_sha256": sha256(setup),
        "source_archive": output.name,
        "source_includes": "runtime, configuration examples, CI and regression-test code",
        "source_excludes": "generated tests/media/screenshots, personal data, tokens and databases",
        "requires_for_local_engine": "Docker Desktop with WSL2 (not bundled)",
        "installer_signed": False,
    }
    names = source_file_inventory(root)
    if output.resolve() == setup.resolve():
        raise RuntimeError("SOURCE_RELEASE_OUTPUT_EQUALS_INSTALLER")
    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"WeiGuang-Math-Source-{version}/"
    hashes = {}
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=8) as archive:
        for relative in names:
            contents = (root / relative).read_bytes()
            hashes[relative] = hashlib.sha256(contents).hexdigest()
            archive.writestr(prefix + relative, contents)
        manifest["source_file_count"] = len(names)
        manifest["source_file_sha256"] = hashes
        archive.writestr(
            prefix + "release-manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
    with ZipFile(output) as archive:
        members = archive.namelist()
        if len(members) != len(names) + 1:
            raise RuntimeError("SOURCE_RELEASE_INCORRECT_CONTENT_COUNT")
        if archive.testzip() is not None:
            raise RuntimeError("SOURCE_RELEASE_CORRUPTED_ZIP")
        for member in members:
            if not member.startswith(prefix) or not is_source_file(
                member.removeprefix(prefix)
            ) and member != prefix + "release-manifest.json":
                raise RuntimeError("SOURCE_RELEASE_UNSAFE_MEMBER: " + member)
        actual = json.loads(archive.read(prefix + "release-manifest.json"))
        if actual["installer_sha256"] != sha256(setup):
            raise RuntimeError("SOURCE_RELEASE_INSTALLER_HASH_MISMATCH")
    print(
        "TWO_FILE_WINDOWS_RELEASE_OK", setup.name, output.name,
        len(names), "source files", sha256(setup), sha256(output),
    )
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="1.0.5")
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    build_release(
        setup=args.setup, output=args.output,
        version=args.version, source_sha=args.source_sha,
    )


if __name__ == "__main__":
    main()
