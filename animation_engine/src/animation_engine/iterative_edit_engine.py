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
    flag = root / ".edit_lock"
    try:
        fd = os.open(flag, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise EditEngineError("EDIT_SESSION_LOCKED") from exc
    try:
        with os.fdopen(fd, "w") as f:
            f.write(f"{os.getpid()}\n")
        yield
    finally:
        flag.unlink(missing_ok=True)


def _state(root: Path) -> dict:
    p = Path(root) / _SESSION
    if not p.is_file():
        raise EditEngineError("EDIT_SESSION_NOT_FOUND")
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0" or data.get("mode") != "iterative_video_edit":
        raise EditEngineError("EDIT_SESSION_SCHEMA")
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


def create_session(
    package: Path, baseline_mp4: Path, baseline_manifest: Path,
    root: Path, *, adaptive: bool = True, fps: int = 30,
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
            _publish(v0 / _MOVIE, root / "latest.mp4")
            _publish(v0 / _MANIFEST, root / "latest_manifest.json")
            _publish(v0 / _SUBTITLE, root / "latest.srt")
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
                   *, fps: int, adaptive: bool) -> dict:
    from .spoken_movie import render_spoken_classroom
    return render_spoken_classroom(
        package / "spoken_classroom.json",
        output_mp4=movie, output_json=manifest,
        output_srt=subtitles, fps=fps, adaptive=adaptive,
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
            plan = agent(instruction, folder / "package", state["history"])
            if not isinstance(plan, dict):
                raise EditEngineError("EDIT_AGENT_DID_NOT_RETURN_PLAN")
            attempt["model"] = plan.get("model")
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
            movie, manifest, subtitles = (
                folder / _MOVIE, folder / _MANIFEST, folder / _SUBTITLE
            )
            report = renderer(
                folder / "package", movie, manifest, subtitles,
                fps=state["fps"], adaptive=state["adaptive"],
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
            _publish(version / _MOVIE, root / "latest.mp4")
            _publish(version / _MANIFEST, root / "latest_manifest.json")
            _publish(version / _SUBTITLE, root / "latest.srt")
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
            "error": attempt["error"],
        }


def record_feedback(root: Path, feedback: str, *, satisfied: bool = False) -> dict:
    """An unsatisfied round is followed by another edit of the latest result."""
    root = Path(root)
    if not isinstance(feedback, str) or not feedback.strip():
        raise EditEngineError("EDIT_FEEDBACK_EMPTY")
    with session_lock(root):
        state = _state(root)
        if not state["history"] or state["history"][-1]["status"] not in (
                "preview_ready", "accepted", "needs_revision"):
            raise EditEngineError("EDIT_FEEDBACK_NO_CURRENT_PREVIEW")
        last = state["history"][-1]
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
    state = _state(Path(root))
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
    output = Path(output)
    if output.suffix.lower() != ".json":
        raise EditEngineError("EDIT_ONLY_JSON_EXPORT")
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
