"""Safe multi-file artifact publication and source/output path isolation.

An output failure must never remove a previously successful movie/manifest.
All temporary files and backups live on the target filesystem so os.replace
is atomic for each individual file. A multi-file commit is compensated with
verified backups if a later rename fails.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Mapping


class OutputSafetyError(ValueError):
    pass


def _aliases(a: Path, b: Path) -> bool:
    if a.resolve() == b.resolve():
        return True
    try:
        return a.is_file() and b.is_file() and os.path.samefile(a, b)
    except OSError:
        return False


def validate_output_targets(
    outputs: Mapping[Path, str], *, protected=(),
) -> None:
    """Refuse duplicate, invalid, symlinked or source-aliasing output paths."""
    destinations = [Path(p) for p in outputs]
    for i, path in enumerate(destinations):
        expected = outputs[path]
        if (path.suffix.lower() != expected or path.is_symlink()
                or path.is_dir()):
            raise OutputSafetyError("OUTPUT_INVALID_TARGET: " + str(path))
        if any(_aliases(path, prior) for prior in destinations[:i]):
            raise OutputSafetyError("OUTPUT_TARGET_COLLISION: " + str(path))
        if any(_aliases(path, Path(source)) for source in protected):
            raise OutputSafetyError("OUTPUT_OVERWRITES_SOURCE: " + str(path))


def course_source_files(source: Path, *, allow_script_export: bool = False):
    """Treat all authored JSON within a source package as protected.

    Known generated movie report filenames are excluded so a user can rerun
    a video into the same output files. An unknown JSON is protected by default.
    """
    root = Path(source).parent
    generated = {
        "movie_manifest.json", "render_report.json",
        "video_manifest.json", "manifest.json", "latest_manifest.json",
    }
    return [
        file for file in root.rglob("*.json")
        if file.is_file() and not (
            file.parent == root and (
                file.name in generated or (
                    allow_script_export and file.name == "lesson_script.json"
                )
            )
        )
    ]


def publish_bundle(
    outputs: Mapping[Path, Path | bytes], *, suffixes: Mapping[Path, str],
    protected=(),
) -> None:
    """Stage all outputs first, publish, and restore old outputs on errors."""
    files = {Path(target): value for target, value in outputs.items()}
    expected = {Path(target): suffix for target, suffix in suffixes.items()}
    if set(files) != set(expected):
        raise OutputSafetyError("OUTPUT_BUNDLE_TARGET_MISMATCH")
    validate_output_targets(expected, protected=protected)
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path | None] = {}
    published: list[Path] = []
    rollback_failed = False

    def _temporary(target: Path, prefix: str) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=prefix, dir=str(target.parent))
        os.close(fd)
        return Path(name)

    try:
        for target, content in files.items():
            temp = _temporary(target, ".pending-" + target.name + "-")
            staged[target] = temp
            if isinstance(content, bytes):
                temp.write_bytes(content)
            else:
                source = Path(content)
                if _aliases(target, source):
                    raise OutputSafetyError("OUTPUT_OVERWRITES_SOURCE: " + str(target))
                shutil.copyfile(source, temp)
            backup = None
            if target.exists():
                backup = _temporary(target, ".prior-" + target.name + "-")
                shutil.copyfile(target, backup)
            backups[target] = backup
        for target in files:
            os.replace(staged[target], target)
            published.append(target)
    except Exception:
        # Roll back in reverse order, preserving all previously completed files.
        # If restoration itself fails, keep backups rather than delete them.
        rollback_errors = []
        for target in reversed(published):
            backup = backups.get(target)
            try:
                if backup is not None:
                    os.replace(backup, target)
                    backups[target] = None
                else:
                    target.unlink(missing_ok=True)
            except OSError as exc:
                rollback_errors.append(f"{target}: {type(exc).__name__}")
        if rollback_errors:
            rollback_failed = True
            raise OutputSafetyError(
                "OUTPUT_ROLLBACK_FAILED: " + ", ".join(rollback_errors)
            )
        raise
    finally:
        for temp in staged.values():
            temp.unlink(missing_ok=True)
        # Keep recovery copies if a filesystem failure prevented rollback.
        if not rollback_failed:
            for backup in backups.values():
                if backup is not None:
                    backup.unlink(missing_ok=True)


def ffconcat_file(path: Path) -> str:
    """Quote literal file paths, including apostrophes, for FFmpeg concat."""
    name = Path(path).as_posix()
    if "\n" in name or "\r" in name or "\x00" in name:
        raise OutputSafetyError("FFCONCAT_INVALID_PATH")
    return "file '" + name.replace("'", "'\\''") + "'\n"
