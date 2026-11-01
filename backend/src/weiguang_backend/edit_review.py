"""Resumable natural-language edit review without a waiting render worker.

The model proposes a deterministic JSON patch against a committed session
revision. The candidate is schema/source-validated and stored for inspection.
An approved candidate is re-applied via the original *unchanged* engine
run_edit, with hash-bound reviewers and media verification. No review can
implicitly approve a different model output or a later source revision.
"""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from uuid import uuid4
from typing import Callable

from animation_engine.iterative_edit_engine import (
    session_lock, _state, _copy_current, run_edit,
)
from animation_engine.iterative_edit_ops import (
    EditEngineError, apply_json_operations, validate_teaching_package,
    atomic_json, file_digest,
)


def _source_digests(package: Path) -> dict[str, str]:
    return {
        path.relative_to(package).as_posix(): file_digest(path)
        for path in sorted(package.rglob("*.json"))
    }


def _review_document(path: Path) -> dict:
    file=Path(path)/"review.json"
    if not file.is_file():
        raise EditEngineError("EDIT_PENDING_REVIEW_NOT_FOUND")
    spec=json.loads(file.read_text(encoding="utf-8"))
    if spec.get("schema_version")!="1.0" or spec.get("status") not in (
            "pending","approved"):
        raise EditEngineError("EDIT_REVIEW_INVALID")
    return spec


def prepare_edit_review(
    session: Path, instruction: str,
    *, agent: Callable, reviewer_required: bool=True,
) -> dict:
    """Plan, stage and validate; never render, approve or alter latest video."""
    session=Path(session)
    if not instruction.strip():
        raise EditEngineError("EDIT_INSTRUCTION_EMPTY")
    pending=session/"pending_reviews"/uuid4().hex
    pending.mkdir(parents=True, exist_ok=False)
    try:
        with session_lock(session):
            state=_state(session)
            revision=state["revision"]
            package=pending/"package"
            _copy_current(session/state["latest_package"], package)
            # The proposal needs the same authentic previous-audio timeline
            # and subtitles available to the standard iterative engine.
            manifest=session/"latest_manifest.json"
            if manifest.is_file():
                shutil.copyfile(manifest,pending/"current_timeline.json")
            subtitles=session/"latest.srt"
            if subtitles.is_file():
                shutil.copyfile(subtitles,pending/"current_subtitles.srt")
            plan=agent(instruction,package,state["history"])
            if not isinstance(plan,dict):
                raise EditEngineError("EDIT_AGENT_DID_NOT_RETURN_PLAN")
            operations=apply_json_operations(package,plan)
            checked=validate_teaching_package(
                package,adaptive=state["adaptive"],
            )
            changed=sorted({op["file"] for op in operations})
            spoken=package/"spoken_classroom.json"
            from animation_engine.unified_classroom_flow import _load
            doc=_load(spoken)
            script_text=""
            if "lesson_contract" in doc:
                from animation_engine.spoken_classroom import checked_spoken
                from animation_engine.v27_teacher_contract import export_spoken_script
                reviewed=checked_spoken(spoken,adaptive=state["adaptive"])
                if "spoken_classroom.json" in changed:
                    export_spoken_script(
                        reviewed,output_json=package/"lesson_script.json",
                        output_md=package/"lesson_script.md",
                        source_document=doc,source_path=spoken,
                    )
                script=package/"lesson_script.md"
                if script.is_file():
                    script_text=script.read_text(encoding="utf-8")
            proposal={
                "schema_version":"1.0",
                "status":"pending",
                "instruction":instruction,
                "source_revision":revision,
                "plan":plan,
                "changed":changed,
                "source_spoken_sha256":checked["source_spoken_sha256"],
                "candidate_digests":_source_digests(package),
                "script_sha256":(
                    file_digest(package/"lesson_script.json")
                    if (package/"lesson_script.json").exists() else None
                ),
                "summary":str(len(plan.get("requirements",[])))+" 项修改",
                "reviewer":None,
                "reviewer_required":bool(reviewer_required),
            }
            atomic_json(pending/"review.json",proposal)
        return {
            "review_path":str(pending),
            "source_revision":revision,
            "status":"review_pending",
            "changes":changed,
            "summary":proposal["summary"],
            "script":script_text,
            "requirements":plan["requirements"],
        }
    except Exception:
        shutil.rmtree(pending,ignore_errors=True)
        raise


def view_edit_review(path: Path) -> dict:
    spec=_review_document(path)
    script=Path(path)/"package"/"lesson_script.md"
    return {
        "status":spec["status"],
        "original_instruction":spec["instruction"],
        "source_revision":spec["source_revision"],
        "requirements":spec["plan"]["requirements"],
        "changed_files":spec["changed"],
        "script":script.read_text(encoding="utf-8") if script.is_file() else "",
    }


def mark_edit_review(
    path: Path, *, reviewer: str, confirmed: bool,
    current_revision: int,
) -> dict:
    """Approve only a candidate still identical to the stored staged files."""
    if not reviewer or not reviewer.strip() or confirmed is not True:
        raise EditEngineError("EDIT_EXPLICIT_REVIEW_REQUIRED")
    path=Path(path)
    spec=_review_document(path)
    if spec["status"]!="pending":
        raise EditEngineError("EDIT_REVIEW_ALREADY_DECIDED")
    if spec["source_revision"]!=current_revision:
        raise EditEngineError("EDIT_REVIEW_STALE_REVISION")
    if _source_digests(path/"package")!=spec["candidate_digests"]:
        raise EditEngineError("EDIT_REVIEW_CANDIDATE_CHANGED")
    spec["reviewer"]=reviewer.strip()
    spec["status"]="approved"
    atomic_json(path/"review.json",spec)
    return {"status":"approved","reviewer":spec["reviewer"]}


def reject_edit_review(path: Path) -> None:
    spec=_review_document(path)
    if spec["status"]!="pending":
        raise EditEngineError("EDIT_REVIEW_ALREADY_DECIDED")
    spec["status"]="rejected"
    atomic_json(Path(path)/"review.json",spec)


def render_approved_edit(
    session: Path, pending: Path, *,
    renderer: Callable | None=None,media_check: Callable | None=None,
) -> dict:
    """Execute exactly the reviewed patch with independent engine validation."""
    session,pending=Path(session),Path(pending)
    reviewed=_review_document(pending)
    if reviewed["status"]!="approved":
        raise EditEngineError("EDIT_REVIEW_NOT_APPROVED")
    with session_lock(session):
        current=_state(session)
        if current["revision"]!=reviewed["source_revision"]:
            raise EditEngineError("EDIT_REVIEW_STALE_REVISION")

    approved=reviewed["candidate_digests"]
    def exact_candidate(package: Path):
        return all(
            file_digest(package/name)==digest
            for name,digest in approved.items()
            if name in reviewed["changed"] and (package/name).is_file()
        ) and all(
            (package/name).is_file()
            for name in reviewed["changed"]
        )

    def agent(instruction,package,history):
        if instruction!=reviewed["instruction"]:
            raise EditEngineError("EDIT_REVIEW_INSTRUCTION_CHANGED")
        return copy.deepcopy(reviewed["plan"])

    def math_reviewer(package,changed):
        return exact_candidate(package)

    def script_reviewer(script_md,script_json):
        original=pending/"package"
        if not exact_candidate(script_json.parent):
            return False
        if reviewed["script_sha256"]!=file_digest(script_json):
            return False
        before=original/"lesson_script.md"
        return before.is_file() and file_digest(before)==file_digest(script_md)

    options={"math_reviewer":math_reviewer,"script_reviewer":script_reviewer}
    if renderer is not None:
        options["renderer"]=renderer
    if media_check is not None:
        options["media_check"]=media_check
    return run_edit(session,reviewed["instruction"],agent,**options)
