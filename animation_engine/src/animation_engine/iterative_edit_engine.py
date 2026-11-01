"""V2.6.5 no-UI iterative editing engine.

One current movie. Any number of consecutive free-language edit batches. Each
batch can contain arbitrary many requirements. Only a completely source-valid,
audible, rendered candidate becomes the latest movie; failed edits never
silently replace the current version. Old versions exist only internally for
recovery / JSON training provenance, not for a compare UI.

An AI agent is deliberately a required injectable callable. This library
never pretends that a hard-coded keyword parser understands arbitrary language.
"""
from __future__ import annotations

from .video_settings import DEFAULT_VIDEO_FPS

import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Any

from .iterative_edit_ops import (
    EditEngineError, apply_json_operations, atomic_json,
    file_digest, validate_teaching_package,
)

_MOVIE = "movie.mp4"
_MANIFEST = "movie_manifest.json"
_SUBTITLE = "captions.srt"
_SESSION = "edit_session.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def session_lock(root: Path):
    """OS-held lock: automatically released after crashes, unlike O_EXCL files."""
    flag = root / ".edit_lock"
    fd = os.open(flag, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise EditEngineError("EDIT_SESSION_LOCKED") from exc
        else:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise EditEngineError("EDIT_SESSION_LOCKED") from exc
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode())
        yield
    finally:
        os.close(fd)
        # The lockfile may remain; kernel-held locks never remain after death.


def _state(root: Path) -> dict:
    p = Path(root) / _SESSION
    if not p.is_file():
        raise EditEngineError("EDIT_SESSION_NOT_FOUND")
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0" or data.get("mode") != "iterative_video_edit":
        raise EditEngineError("EDIT_SESSION_SCHEMA")
    # Restore legacy latest.* aliases from the immutable committed revision.
    # If a previous process died between replacing three files, the session
    # revision remains authoritative and none of the mixed aliases survive.
    committed = Path(root) / "versions" / f"{data['revision']:04d}"
    for source_name, alias in (
        (_MOVIE, "latest.mp4"), (_MANIFEST, "latest_manifest.json"),
        (_SUBTITLE, "latest.srt"),
    ):
        source = committed / source_name
        target = Path(root) / alias
        if not source.is_file():
            raise EditEngineError("EDIT_COMMITTED_REVISION_MISSING")
        if not target.is_file() or file_digest(target) != file_digest(source):
            _publish(source, target)
    return data


def _verified_media(path: Path):
    """Require both actual video and audio streams, not a silent placeholder."""
    p = subprocess.run([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)
    ], capture_output=True, text=True)
    if p.returncode:
        raise EditEngineError("EDIT_VIDEO_NOT_PLAYABLE")
    try:
        streams = json.loads(p.stdout)["streams"]
        video = next(x for x in streams if x.get("codec_type") == "video")
        audio = next(x for x in streams if x.get("codec_type") == "audio")
        if (int(video["width"]) < 300 or int(video["height"]) < 200 or
                int(audio["sample_rate"]) < 16000):
            raise ValueError("poor quality")
    except (ValueError, KeyError, StopIteration, TypeError) as exc:
        raise EditEngineError("EDIT_REAL_AUDIO_VIDEO_REQUIRED") from exc


def _validated_render(report: dict, source: dict) -> None:
    if (not isinstance(report, dict) or
            report.get("source_spoken_sha256") != source["source_spoken_sha256"] or
            report.get("source_flow_sha256") != source["source_flow_sha256"] or
            report.get("voice_status") != "real_edge_neural_pcm_verified" or
            report.get("subtitle_status") != "actual_tts_phrase_aligned" or
            report.get("math_caption_renderer") != "true_manim_mathtex" or
            report.get("voiced_action_count") != source["spoken_actions"] or
            report.get("source_narration_action_count") != source["spoken_actions"] or
            report.get("fabricated_voice_or_subtitle_count") != 0 or
            not isinstance(report.get("audio_verification"), dict)):
        raise EditEngineError("EDIT_RENDER_NOT_AUTHENTIC_OR_SOURCE_VERIFIED")


def _copy_current(package: Path, destination: Path) -> None:
    if not package.is_dir():
        raise EditEngineError("EDIT_SOURCE_PACKAGE_MISSING")
    for p in package.rglob("*"):
        if p.is_symlink():
            raise EditEngineError("EDIT_PACKAGE_SYMLINK_NOT_ALLOWED")
        if p.is_file() and p.suffix.lower() not in (
                ".json", ".png", ".jpg", ".jpeg", ".svg"):
            raise EditEngineError("EDIT_UNSAFE_PACKAGE_FILE")
    shutil.copytree(package, destination)


def _publish(source: Path, latest: Path):
    temp = latest.with_name("." + latest.name + "." + str(os.getpid()))
    try:
        shutil.copyfile(source, temp)
        os.replace(temp, latest)
    finally:
        temp.unlink(missing_ok=True)


def _publish_bundle(version: Path, root: Path) -> None:
    """Rollback all aliases on ordinary publish errors.

    A crash is repaired by _state from the immutable committed revision;
    callers must always treat edit_session.json revision as the commit pointer.
    """
    import tempfile
    names = (
        (_MOVIE, "latest.mp4"),
        (_MANIFEST, "latest_manifest.json"),
        (_SUBTITLE, "latest.srt"),
    )
    with tempfile.TemporaryDirectory(prefix=".publish-backup-",dir=root) as backup:
        saved = Path(backup)
        had = set()
        for _, target in names:
            current = root / target
            if current.is_file():
                had.add(target)
                shutil.copyfile(current, saved / target)
        try:
            for source, target in names:
                _publish(version / source, root / target)
        except Exception:
            for _, target in names:
                current = root / target
                if target in had:
                    _publish(saved / target, current)
                else:
                    current.unlink(missing_ok=True)
            raise


def create_session(
    package: Path, baseline_mp4: Path, baseline_manifest: Path,
    root: Path, *, adaptive: bool = True, fps: int = DEFAULT_VIDEO_FPS,
    media_check: Callable[[Path], Any] = _verified_media,
) -> dict:
    """Initialize on an already verified V2.6.4 lesson, not dummy speech."""
    package = Path(package)
    root = Path(root)
    if root.exists():
        raise EditEngineError("EDIT_SESSION_ALREADY_EXISTS")
    if type(fps) is not int or not 8 <= fps <= 60:
        raise EditEngineError("EDIT_FPS_INVALID")
    root.mkdir(parents=True)
    try:
        with session_lock(root):
            v0 = root / "versions" / "0000"
            v0.parent.mkdir()
            _copy_current(package, v0 / "package")
            checked = validate_teaching_package(v0 / "package", adaptive=adaptive)
            report = json.loads(Path(baseline_manifest).read_text(encoding="utf-8"))
            _validated_render(report, checked)
            media_check(Path(baseline_mp4))
            shutil.copyfile(baseline_mp4, v0 / _MOVIE)
            atomic_json(v0 / _MANIFEST, report)
            if (Path(baseline_mp4).with_suffix(".srt")).exists():
                shutil.copyfile(Path(baseline_mp4).with_suffix(".srt"),
                                v0 / _SUBTITLE)
            else:
                (v0 / _SUBTITLE).write_text("", encoding="utf-8")
            _publish_bundle(v0, root)
            state = {
                "schema_version": "1.0", "mode": "iterative_video_edit",
                "created_at": _now(), "updated_at": _now(),
                "adaptive": adaptive, "fps": fps,
                "revision": 0, "attempt": 0,
                "satisfied": False,
                "latest_movie": "latest.mp4",
                "latest_package": "versions/0000/package",
                "latest_source_spoken_sha256": checked["source_spoken_sha256"],
                "history": [],
            }
            atomic_json(root / _SESSION, state)
            return state
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


def _real_renderer(package: Path, movie: Path, manifest: Path, subtitles: Path,
                   *, fps: int, adaptive: bool, cache_dir: Path | None=None) -> dict:
    from .spoken_movie import render_spoken_classroom
    return render_spoken_classroom(
        package / "spoken_classroom.json",
        output_mp4=movie, output_json=manifest,
        output_srt=subtitles, fps=fps, adaptive=adaptive,
        cache_dir=cache_dir,
    )


def run_edit(
    root: Path, instruction: str,
    agent: Callable[[str, Path, list[dict]], dict], *,
    renderer: Callable[..., dict] = _real_renderer,
    math_reviewer: Callable[[Path, list[str]], bool] | None = None,
    media_check: Callable[[Path], Any] = _verified_media,
) -> dict:
    """Apply one arbitrary-language/multi-requirement batch to LATEST source.

    Agent must return a structured revision plan. It never receives a mutable
    copy of prior versions; all actual package edits go through reviewed JSON
    operations and mathematical provenance checks.
    """
    root = Path(root)
    if not isinstance(instruction, str) or not instruction.strip():
        raise EditEngineError("EDIT_INSTRUCTION_EMPTY")
    with session_lock(root):
        state = _state(root)
        next_attempt = state["attempt"] + 1
        next_version = state["revision"] + 1
        attempt = {
            "attempt_id": f"attempt_{next_attempt:04d}",
            "submitted_at": _now(),
            "original_instruction": instruction,
            "source_revision": state["revision"],
            "result_revision": None,
            "status": "failed",
            "requirements": [], "operations": [],
            "model": None, "error": None,
            "feedback": None, "satisfied": False,
        }
        folder = root / "attempts" / f"{next_attempt:04d}"
        folder.parent.mkdir(exist_ok=True)
        if folder.exists():
            shutil.rmtree(folder)
        try:
            _copy_current(root / state["latest_package"], folder / "package")
            # The AI sees the real latest video clock, event/action timings,
            # captions and spoken words: "minute six" or "that equation"
            # must resolve against the CURRENT movie, not the baseline.
            shutil.copyfile(
                root / "latest_manifest.json",
                folder / "current_timeline.json",
            )
            if (root / "latest.srt").is_file():
                shutil.copyfile(
                    root / "latest.srt",
                    folder / "current_subtitles.srt",
                )
            plan = agent(instruction, folder / "package", state["history"])
            if not isinstance(plan, dict):
                raise EditEngineError("EDIT_AGENT_DID_NOT_RETURN_PLAN")
            attempt["model"] = plan.get("model")
            if isinstance(plan.get("requirements"), list):
                attempt["requirements"] = [
                    {**req, "status": "planned"}
                    for req in plan["requirements"]
                    if isinstance(req, dict)
                ]
            operations = apply_json_operations(folder / "package", plan)
            attempt["operations"] = operations
            attempt["requirements"] = [
                {**req, "status": "completed"} for req in plan["requirements"]
            ]
            changed = sorted({op["file"] for op in operations})
            mathematical_sources = [
                x for x in changed if x not in (
                    "spoken_classroom.json", "adaptive_layout.json"
                )
            ]
            if mathematical_sources:
                if math_reviewer is None or math_reviewer(
                        folder / "package", mathematical_sources) is not True:
                    raise EditEngineError("EDIT_MATH_REVIEW_REQUIRED")
            checked = validate_teaching_package(
                folder / "package", adaptive=state["adaptive"]
            )
            from .edit_impact import analyze_impact
            attempt["impact"]=analyze_impact(
                root / state["latest_package"],
                folder / "package", operations,
            )
            movie, manifest, subtitles = (
                folder / _MOVIE, folder / _MANIFEST, folder / _SUBTITLE
            )
            options={"fps":state["fps"], "adaptive":state["adaptive"]}
            # Preserve the V2.6.5 extension point: custom rendering agents
            # are not silently given a new keyword they cannot accept.
            if renderer is _real_renderer:
                options["cache_dir"]=root / "render_cache"
            report = renderer(
                folder / "package", movie, manifest, subtitles, **options,
            )
            if not movie.is_file() or not manifest.is_file():
                raise EditEngineError("EDIT_MOVIE_OR_AUDIT_MISSING")
            actual = json.loads(manifest.read_text(encoding="utf-8"))
            _validated_render(actual, checked)
            if isinstance(report, dict) and (
                    report.get("source_spoken_sha256") !=
                    checked["source_spoken_sha256"]):
                raise EditEngineError("EDIT_RENDER_RETURN_MISMATCH")
            media_check(movie)
            if not subtitles.is_file():
                raise EditEngineError("EDIT_REAL_SUBTITLE_FILE_MISSING")
            version = root / "versions" / f"{next_version:04d}"
            if version.exists():
                raise EditEngineError("EDIT_VERSION_ALREADY_EXISTS")
            version.parent.mkdir(exist_ok=True)
            os.replace(folder, version)
            _publish_bundle(version, root)
            attempt["cache_stats"]=actual.get("incremental_cache")
            attempt["render_timings_seconds"]=actual.get("render_timings_seconds")
            attempt.update({
                "status": "preview_ready",
                "result_revision": next_version,
                "source_sha256": checked["source_spoken_sha256"],
                "result_movie_sha256": file_digest(version / _MOVIE),
                "rendered_at": _now(),
            })
            state.update({
                "revision": next_version,
                "latest_package": f"versions/{next_version:04d}/package",
                "latest_source_spoken_sha256": checked["source_spoken_sha256"],
                "satisfied": False,
            })
        except Exception as exc:
            attempt["error"] = (
                f"{type(exc).__name__}: {str(exc)[:700]}"
            )
            # In addition to restoring the latest aliases, remove a staged
            # version that was already moved out of attempts before publishing
            # failed; otherwise retrying the same revision would be blocked.
            if "version" in locals() and version.exists() and state["revision"] < next_version:
                shutil.rmtree(version, ignore_errors=True)
            # Missing output, bad math or TTS failure must never change the
            # user-visible latest movie.
            shutil.rmtree(folder, ignore_errors=True)
        state["attempt"] = next_attempt
        state["updated_at"] = _now()
        state["history"].append(attempt)
        atomic_json(root / _SESSION, state)
        return {
            "status": attempt["status"],
            "attempt_id": attempt["attempt_id"],
            "latest_movie": str(root / "latest.mp4"),
            "revision": state["revision"],
            "requirements": attempt["requirements"],
            "impact": attempt.get("impact"),
            "cache_stats": attempt.get("cache_stats"),
            "error": attempt["error"],
        }


def record_feedback(root: Path, feedback: str, *, satisfied: bool = False) -> dict:
    """An unsatisfied round is followed by another edit of the latest result."""
    root = Path(root)
    if not isinstance(feedback, str) or not feedback.strip():
        raise EditEngineError("EDIT_FEEDBACK_EMPTY")
    with session_lock(root):
        state = _state(root)
        # A failed request never replaces the current movie. Feedback must
        # still be possible on the most recent successfully rendered preview.
        last = next((
            row for row in reversed(state["history"])
            if row.get("result_revision") == state["revision"]
            and row.get("status") in (
                "preview_ready", "accepted", "needs_revision"
            )
        ), None)
        if last is None:
            raise EditEngineError("EDIT_FEEDBACK_NO_CURRENT_PREVIEW")
        last["feedback"] = feedback
        last["satisfied"] = bool(satisfied)
        last["status"] = "accepted" if satisfied else "needs_revision"
        state["satisfied"] = bool(satisfied)
        state["updated_at"] = _now()
        atomic_json(root / _SESSION, state)
        return {
            "status": last["status"], "latest_movie": str(root / "latest.mp4"),
            "revision": state["revision"], "satisfied": state["satisfied"],
        }


def export_history(root: Path, output: Path) -> dict:
    """The sole outward training-data export is a complete UTF-8 JSON file."""
    output = Path(output)
    if output.suffix.lower() != ".json":
        raise EditEngineError("EDIT_ONLY_JSON_EXPORT")
    root = Path(root)
    # Export the complete history from one committed revision. _state may
    # repair crash-interrupted latest.* aliases, so it also needs the lock.
    # Never overwrite the session journal or an immutable video revision.
    destination = output.resolve()
    if (destination == (root / _SESSION).resolve()
            or destination.is_relative_to((root / "versions").resolve())
            or destination.is_relative_to((root / "attempts").resolve())):
        raise EditEngineError("EDIT_EXPORT_PROTECTED_PATH")
    with session_lock(root):
        state = _state(root)
        export = {
            "schema_version": "1.0", "mode": "iterative_edit_training_export",
            "created_at": state["created_at"],
            "exported_at": _now(),
            "current_revision": state["revision"],
            "current_satisfied": state["satisfied"],
            "rounds": state["history"],
            "notes": {
                "raw_instructions_preserved": True,
                "failed_and_rejected_rounds_included": True,
                "user_feedback_preserved": True,
                "no_automatic_external_upload": True,
                "media_not_embedded": True,
            },
        }
        atomic_json(output, export)
    return export


def plan_from_file(path: Path):
    """Deterministic, inspectable input adapter for a prepared multi-edit plan.

    A real model provider can instead implement the run_edit agent callable,
    producing the exact same open-ended structured plan from user language.
    """
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    def agent(instruction: str, package: Path, history: list[dict]) -> dict:
        return doc
    return agent
