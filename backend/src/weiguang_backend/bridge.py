"""Explicit boundary to the already validated MathTeacher/Manim engine.

Never fabricate a lesson, approval, MP4, mathematical reviewer, or video
result when the original source contracts cannot be satisfied.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable


class BridgeError(ValueError):
    pass


ALLOWED_UPLOADS = {".json", ".md", ".png", ".jpg", ".jpeg", ".svg"}
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_UNCOMPRESSED = 180 * 1024 * 1024


def extract_engine_package(data: bytes, destination: Path,
                           *, problem: str, reference_solution: str) -> dict:
    """Strictly unpack and verify one authored engine course package."""
    from animation_engine.unified_classroom_flow import canonical_sha, checked_flow
    from animation_engine.spoken_classroom import checked_spoken
    if len(data) > MAX_ARCHIVE_BYTES:
        raise BridgeError("PACKAGE_ARCHIVE_TOO_LARGE")
    destination = Path(destination)
    with tempfile.TemporaryDirectory(prefix="wg-package-") as temp:
        staged = Path(temp) / "package"
        staged.mkdir()
        try:
            with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
                entries = archive.infolist()
                if not entries or len(entries) > 350:
                    raise BridgeError("PACKAGE_INVALID_ENTRY_COUNT")
                total = sum(info.file_size for info in entries)
                if total > MAX_UNCOMPRESSED:
                    raise BridgeError("PACKAGE_UNCOMPRESSED_TOO_LARGE")
                for info in entries:
                    name = info.filename.replace("\\", "/")
                    parts = Path(name).parts
                    if (name.startswith("/") or not parts
                            or any(p in ("..", ".") for p in parts)
                            or ":" in name or "\x00" in name
                            or ((info.external_attr >> 16) & 0o170000) == 0o120000):
                        raise BridgeError("PACKAGE_UNSAFE_ENTRY")
                    if info.is_dir():
                        continue
                    if Path(name).suffix.lower() not in ALLOWED_UPLOADS:
                        raise BridgeError("PACKAGE_UNSUPPORTED_ENTRY")
                    target = staged.joinpath(*parts)
                    if not target.resolve().is_relative_to(staged.resolve()):
                        raise BridgeError("PACKAGE_UNSAFE_ENTRY")
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with archive.open(info) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src,dst)
        except (zipfile.BadZipFile, OSError) as exc:
            raise BridgeError("PACKAGE_BAD_ZIP") from exc
        flow_path = staged / "unified_flow.json"
        spoken_path = staged / "spoken_classroom.json"
        if not flow_path.is_file() or not spoken_path.is_file():
            raise BridgeError("PACKAGE_MISSING_ENGINE_CONTRACTS")
        flow = checked_flow(flow_path)
        if flow.problem != problem or canonical_sha(reference_solution) != (
                json.loads(flow_path.read_text(encoding="utf-8"))
                ["reference_solution_sha256"]):
            raise BridgeError("PACKAGE_SOURCE_DOES_NOT_MATCH_LESSON")
        spoken = checked_spoken(spoken_path, adaptive=False)
        if spoken.flow.source_sha256 != flow.source_sha256:
            raise BridgeError("PACKAGE_SPOKEN_FLOW_MISMATCH")
        destination.parent.mkdir(parents=True,exist_ok=True)
        # Validate the entire new course first, then archive and replace.
        # A source edit must not be permanently blocked by an older package.
        archived = None
        if destination.exists():
            from uuid import uuid4
            archived = (destination.parent/"previous_packages"/uuid4().hex)
            archived.parent.mkdir(parents=True,exist_ok=True)
            os.replace(destination,archived)
        try:
            shutil.copytree(staged,destination)
        except Exception:
            shutil.rmtree(destination,ignore_errors=True)
            if archived is not None:
                os.replace(archived,destination)
            raise
        return {"events":len(spoken.events),"source_sha256":spoken.source_sha256}


def export_script(package: Path) -> str:
    from animation_engine.spoken_classroom import checked_spoken
    from animation_engine.v27_teacher_contract import export_spoken_script
    package = Path(package)
    source = package / "spoken_classroom.json"
    reviewed = checked_spoken(source,adaptive=False)
    from animation_engine.unified_classroom_flow import _load
    export_spoken_script(
        reviewed,
        output_json=package / "lesson_script.json",
        output_md=package / "lesson_script.md",
        source_document=_load(source), source_path=source,
    )
    return (package / "lesson_script.md").read_text(encoding="utf-8")


def approve_script(package: Path, reviewer: str) -> dict:
    from animation_engine.spoken_classroom import checked_spoken
    from animation_engine.v27_teacher_contract import approve_prerender_script
    source = Path(package) / "spoken_classroom.json"
    return approve_prerender_script(
        checked_spoken(source,adaptive=False), source,
        reviewer=reviewer, confirmed=True,
    )


def render_package(
    package: Path, output: Path, *, fps: int = 60,
    renderer: Callable | None = None,
) -> tuple[Path, Path, Path, dict]:
    """Return only verified published output, never a demo/mock video."""
    from animation_engine.spoken_movie import render_spoken_classroom
    from animation_engine.spoken_classroom import checked_spoken
    from animation_engine.v27_teacher_contract import require_prerender_script
    package, output = Path(package), Path(output)
    source = package / "spoken_classroom.json"
    reviewed = checked_spoken(source,adaptive=False)
    if "lesson_contract" in json.loads(source.read_text(encoding="utf-8")):
        require_prerender_script(reviewed,source)
    output.mkdir(parents=True,exist_ok=True)
    movie,manifest,subtitle=(
        output/"latest.mp4",output/"latest_manifest.json",output/"latest.srt"
    )
    work = renderer or render_spoken_classroom
    report = work(
        source, output_mp4=movie, output_json=manifest,
        output_srt=subtitle, fps=fps, adaptive=False,
    )
    if not all(p.is_file() for p in (movie,manifest,subtitle)):
        raise BridgeError("RENDER_ARTIFACTS_MISSING")
    if renderer is None:
        from animation_engine.iterative_edit_engine import (
            _verified_media, _validated_render,
        )
        from animation_engine.iterative_edit_ops import validate_teaching_package
        _verified_media(movie)
        _validated_render(
            report, validate_teaching_package(package,adaptive=False),
        )
    # Test injection is permitted only through an explicitly injected callable,
    # never through an HTTP request or production environment flag.
    return movie,manifest,subtitle,report


def initialize_edit(
    package: Path, movie: Path, manifest: Path, session: Path,
    *, fps: int=60, verify_media: Callable | None=None,
) -> dict:
    from animation_engine.iterative_edit_engine import create_session
    options = {"adaptive":False,"fps":fps}
    if verify_media is not None:
        options["media_check"] = verify_media
    return create_session(package,movie,manifest,session,**options)


def run_real_edit(session: Path, instruction: str, *, ai_config: Path,
                  math_reviewer=None, script_reviewer=None) -> dict:
    from animation_engine.iterative_ai_adapter import make_openai_compatible_agent
    from animation_engine.iterative_edit_engine import run_edit
    if not ai_config.is_file():
        raise BridgeError("EDIT_AI_CONFIGURATION_REQUIRED")
    return run_edit(
        session,instruction,make_openai_compatible_agent(ai_config),
        math_reviewer=math_reviewer,script_reviewer=script_reviewer,
    )



def prepare_teacher_draft(
    *, problem: str, reference_solution: str, output: Path,
) -> dict:
    """Run authentic MathTeacher A/B/C; never mislabel it an engine package.

    A complete source-approved voiced course still requires conversion to the
    strict unified-flow/spoken-classroom contract and teacher review.
    """
    from math_teacher.models import TeacherInput
    from math_teacher.pipeline import MathTeacherPipeline
    from math_teacher.provider import OpenAICompatibleJsonModel
    provider=OpenAICompatibleJsonModel()
    candidate=MathTeacherPipeline(provider).run(
        TeacherInput(problem=problem,reference_solution=reference_solution),
        allow_needs_review=True,
    )
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    payload=candidate.model_dump(mode="json")
    from animation_engine.iterative_edit_ops import atomic_json
    atomic_json(output,payload)
    return {
        "status":"teacher_draft_needs_review",
        "validation":payload["validation"],
        "candidate_sha256":candidate.validated_content_sha256,
    }
