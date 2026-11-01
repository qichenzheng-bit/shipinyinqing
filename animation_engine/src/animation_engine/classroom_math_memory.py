"""V2.6.3 source-verified classroom mathematics memory.

The renderer remembers teacher-authored mathematical statements, not hidden
model reasoning. A restatement must be byte-for-byte the same reviewed LaTex;
a dependency declares a citation but does NOT claim to prove a new formula.
The plan fails closed on premature facts, other problems, false branches, and
missing case coverage.
"""
from __future__ import annotations

from .video_settings import DEFAULT_VIDEO_FPS

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .longboard_plan import LongboardError, _sources
from .models import ExecutionPlan
from .proof_chain import checked_proof_chain
from .unified_classroom_flow import (
    Flow, canonical_sha, checked_flow, plan_flow, render_flow, _load,
)

ROOT_FIELDS = frozenset({
    "schema_version", "mode", "teacher_reviewed", "source_flow_sha256",
    "facts", "recalls", "case_merges",
})
FACT_FIELDS = frozenset({
    "fact_id", "stage_id", "event_id", "object_id", "status", "scope",
})
RECALL_FIELDS = frozenset({
    "recall_id", "fact_id", "stage_id", "event_id",
    "to_object_id", "mode", "active_scope",
})
MERGE_FIELDS = frozenset({
    "merge_id", "stage_id", "event_id", "to_object_id",
    "case_group", "case_fact_ids",
})
SCOPE_FIELDS = frozenset({"kind", "case_group", "case_id"})
STATUSES = frozenset({"given", "established"})
MODES = frozenset({"restate", "dependency"})
GLOBAL_SCOPE = {"kind": "global", "case_group": None, "case_id": None}


@dataclass(frozen=True)
class MemoryFact:
    fact_id: str
    stage_id: str
    event_id: str
    object_id: str
    latex: str
    status: str
    scope: dict
    position: tuple[int, int]


@dataclass(frozen=True)
class MemoryContract:
    flow: Flow
    flow_file: Path
    manifest_sha256: str
    facts: tuple[MemoryFact, ...]
    recalls: tuple[dict, ...]
    merges: tuple[dict, ...]

    def event_memory(self, stage_id: str, event_id: str) -> dict:
        return {
            "established": [fact.fact_id for fact in self.facts
                            if (fact.stage_id, fact.event_id) == (stage_id, event_id)],
            "recalled": [row["recall_id"] for row in self.recalls
                         if (row["stage_id"], row["event_id"]) == (stage_id, event_id)],
            "merged": [row["merge_id"] for row in self.merges
                       if (row["stage_id"], row["event_id"]) == (stage_id, event_id)],
        }


def _ident(value: Any) -> bool:
    return isinstance(value, str) and value.isidentifier()


def _scope(value: Any) -> dict:
    if not isinstance(value, dict) or set(value) != SCOPE_FIELDS:
        raise LongboardError("MEMORY_INVALID_SCOPE_FIELDS")
    kind, group, case = value["kind"], value["case_group"], value["case_id"]
    if kind == "global" and group is None and case is None:
        return dict(GLOBAL_SCOPE)
    if kind == "case" and _ident(group) and _ident(case):
        return dict(value)
    raise LongboardError("MEMORY_INVALID_SCOPE")


def _event_meta(flow: Flow):
    """Only include source actions truly displayed in teacher event order."""
    result = {}
    for si, stage in enumerate(flow.stages):
        plan = ExecutionPlan.model_validate(stage.execution)
        maths = _sources(plan)
        proof = None
        if stage.engine == "proof":
            proof = checked_proof_chain(stage.special, stage.storyboard, stage.execution)
        for ei, scene in enumerate(plan.scenes):
            written = {
                action.object_id
                for action in scene.actions
                if action.kind in ("progressive_write", "restore")
                and action.to_region != "question"
            }
            result[(stage.stage_id, scene.event_id)] = {
                "position": (si, ei),
                "written": written,
                "maths": maths,
                "stage": stage,
                "proof": proof,
                "proof_event": proof.for_event(scene.event_id) if proof is not None else None,
            }
    return result


def checked_memory(input_file: Path | str) -> MemoryContract:
    path = Path(input_file).resolve()
    source = _load(path)
    if (set(source) != ROOT_FIELDS or source["schema_version"] != "1.0"
            or source["mode"] != "verified_classroom_memory"
            or source["teacher_reviewed"] is not True):
        raise LongboardError("MEMORY_INVALID_MANIFEST")
    flow_path = path.parent / "unified_flow.json"
    flow = checked_flow(flow_path)
    if source["source_flow_sha256"] != flow.source_sha256:
        raise LongboardError("MEMORY_FLOW_SOURCE_MUTATION")
    meta = _event_meta(flow)
    facts_by_id: dict[str, MemoryFact] = {}
    records = source["facts"]
    if not isinstance(records, list) or not records or len(records) > 100:
        raise LongboardError("MEMORY_FACT_COVERAGE")
    for row in records:
        if not isinstance(row, dict) or set(row) != FACT_FIELDS:
            raise LongboardError("MEMORY_FACT_FIELDS")
        fid = row["fact_id"]
        if not _ident(fid) or fid in facts_by_id or row["status"] not in STATUSES:
            raise LongboardError("MEMORY_DUPLICATE_OR_UNPROVED_FACT")
        key = (row["stage_id"], row["event_id"])
        data = meta.get(key)
        if data is None or row["object_id"] not in data["written"]:
            raise LongboardError("MEMORY_SOURCE_NOT_WRITTEN")
        scope = _scope(row["scope"])
        pe = data["proof_event"]
        if scope["kind"] == "case":
            if (pe is None or pe.case_group != scope["case_group"]
                    or pe.case_id != scope["case_id"]):
                raise LongboardError("MEMORY_CASE_ORIGIN_NOT_PROVED")
        elif pe is not None and pe.case_group is not None:
            raise LongboardError("MEMORY_CASE_FACT_CANNOT_BE_GLOBAL")
        proof = data["proof"]
        if proof is not None and row["object_id"] == proof.goal_id:
            raise LongboardError("MEMORY_GOAL_NOT_ESTABLISHED")
        # The source's teacher-reviewed label is provenance, NOT a formal proof.
        facts_by_id[fid] = MemoryFact(
            fid, key[0], key[1], row["object_id"],
            data["maths"][row["object_id"]]["latex"], row["status"],
            scope, data["position"],
        )
    ordered_facts = tuple(sorted(facts_by_id.values(), key=lambda x: x.position))
    recalls = source["recalls"]
    if not isinstance(recalls, list) or len(recalls) > 150:
        raise LongboardError("MEMORY_RECALL_COVERAGE")
    seen_recalls = set()
    audited_recalls = []
    for row in recalls:
        if not isinstance(row, dict) or set(row) != RECALL_FIELDS:
            raise LongboardError("MEMORY_RECALL_FIELDS")
        ident = row["recall_id"]
        if not _ident(ident) or ident in seen_recalls:
            raise LongboardError("MEMORY_DUPLICATE_RECALL")
        seen_recalls.add(ident)
        origin = facts_by_id.get(row["fact_id"])
        if origin is None:
            raise LongboardError("MEMORY_UNREGISTERED_FACT")
        key = (row["stage_id"], row["event_id"])
        dest = meta.get(key)
        if dest is None or row["to_object_id"] not in dest["written"]:
            raise LongboardError("MEMORY_RECALL_NOT_WRITTEN")
        if dest["position"] <= origin.position:
            raise LongboardError("MEMORY_PREMATURE_OR_SELF_CITATION")
        if row["mode"] not in MODES:
            raise LongboardError("MEMORY_RECALL_MODE")
        active = _scope(row["active_scope"])
        # Case-specific propositions cannot escape their verified case.
        if origin.scope["kind"] == "case":
            if active != origin.scope:
                raise LongboardError("MEMORY_CASE_SCOPE_LEAK")
            pe = dest["proof_event"]
            if pe is None or (pe.case_group, pe.case_id) != (
                    active["case_group"], active["case_id"]):
                raise LongboardError("MEMORY_CASE_DESTINATION_UNVERIFIED")
        elif active["kind"] == "case":
            pe = dest["proof_event"]
            if pe is None or (pe.case_group, pe.case_id) != (
                    active["case_group"], active["case_id"]):
                raise LongboardError("MEMORY_ACTIVE_SCOPE_INVENTED")
        target_latex = dest["maths"][row["to_object_id"]]["latex"]
        if row["mode"] == "restate" and target_latex != origin.latex:
            raise LongboardError("MEMORY_RESTATEMENT_MATH_MUTATED")
        audited_recalls.append({
            **row,
            "source_stage_id": origin.stage_id,
            "source_event_id": origin.event_id,
            "source_object_id": origin.object_id,
            "source_latex": origin.latex,
            "target_latex": target_latex,
            "source_status": origin.status,
            "verified_before_use": True,
            "source_scope": dict(origin.scope),
            "is_literal_restatement": row["mode"] == "restate",
            "reasoning_truth_status": "teacher_reviewed_not_formally_proven",
        })
    merges = source["case_merges"]
    if not isinstance(merges, list) or len(merges) > 30:
        raise LongboardError("MEMORY_MERGE_COVERAGE")
    seen_merges = set()
    verified_merges = []
    for row in merges:
        if not isinstance(row, dict) or set(row) != MERGE_FIELDS:
            raise LongboardError("MEMORY_MERGE_FIELDS")
        mid, group = row["merge_id"], row["case_group"]
        if not _ident(mid) or mid in seen_merges:
            raise LongboardError("MEMORY_DUPLICATE_MERGE")
        seen_merges.add(mid)
        dest = meta.get((row["stage_id"], row["event_id"]))
        if dest is None or row["to_object_id"] not in dest["written"]:
            raise LongboardError("MEMORY_MERGE_NOT_WRITTEN")
        selected = row["case_fact_ids"]
        if (not _ident(group) or not isinstance(selected, list)
                or not selected or len(selected) != len(set(selected))):
            raise LongboardError("MEMORY_MERGE_BAD_COVERAGE")
        candidates = [facts_by_id.get(x) for x in selected]
        if any(x is None or x.scope["kind"] != "case"
               or x.scope["case_group"] != group
               or x.position >= dest["position"] for x in candidates):
            raise LongboardError("MEMORY_MERGE_PREMATURE_OR_WRONG_CASE")
        contracts = [info["proof"] for info in meta.values()
                     if info["proof"] is not None]
        declared = [
            g for contract in contracts for g in contract.branch_groups
            if g["group_id"] == group
        ]
        if not declared:
            raise LongboardError("MEMORY_UNDECLARED_CASE_GROUP")
        coverage = {
            fact.scope["case_id"] for fact in candidates
        }
        expected = set(declared[0]["cases"])
        if coverage != expected:
            raise LongboardError("MEMORY_INCOMPLETE_CASE_COVERAGE")
        if dest["proof"] is not None and (
                dest["proof_event"].role != "merge"
                or dest["proof_event"].event_id != declared[0]["merge_event_id"]):
            raise LongboardError("MEMORY_MERGE_NOT_A_PROOF_MERGE")
        verified_merges.append({
            **row, "covered_cases": sorted(coverage),
            "case_coverage_verified": True,
            "conclusion_teacher_reviewed_not_formally_proven": True,
        })
    return MemoryContract(
        flow, flow_path, canonical_sha(source), ordered_facts,
        tuple(audited_recalls), tuple(verified_merges),
    )


def _memory_audit(contract: MemoryContract) -> dict:
    return {
        "schema_version": "1.0",
        "mode": "verified_classroom_memory",
        "source_memory_sha256": contract.manifest_sha256,
        "source_flow_sha256": contract.flow.source_sha256,
        "fact_count": len(contract.facts),
        "recall_count": len(contract.recalls),
        "case_merge_count": len(contract.merges),
        "facts": [{
            "fact_id": f.fact_id, "stage_id": f.stage_id,
            "event_id": f.event_id, "object_id": f.object_id,
            "latex": f.latex, "status": f.status, "scope": f.scope,
            "global_source_order": list(f.position),
        } for f in contract.facts],
        "recalls": list(contract.recalls),
        "case_merges": list(contract.merges),
        "mathematical_truth_status": "teacher_reviewed_not_formally_proven",
    }


def plan_memory(input_file: Path | str, *, measure=None,
                adaptive: bool = False) -> dict:
    memory = checked_memory(input_file)
    if adaptive:
        from .adaptive_classroom_flow import plan_adaptive_flow
        base = plan_adaptive_flow(Path(input_file).parent / "adaptive_layout.json",
                                  measure=measure)
    else:
        base = plan_flow(memory.flow_file, measure=measure)
    events = base["events"]
    positions = {(event["stage_id"], event["event_id"]) for event in events}
    for event in events:
        event["memory"] = memory.event_memory(event["stage_id"], event["event_id"])
    for f in memory.facts:
        if (f.stage_id, f.event_id) not in positions:
            raise LongboardError("MEMORY_EVENT_MISSING_FROM_PLAN")
    return {
        **base,
        "memory": _memory_audit(memory),
        "memory_contract_validated": True,
        "cross_stage_memory_strategy": "verified_original_mathematics_rewritten_only_when_authored",
        "voice_status": "not_recorded",
        "subtitle_status": "not_audio_aligned",
    }


def render_memory(input_file: Path | str, *,
                  output_mp4: Path, output_json: Path,
                  fps: int = DEFAULT_VIDEO_FPS, adaptive: bool = False) -> dict:
    memory = checked_memory(input_file)
    plan = plan_memory(input_file, adaptive=adaptive)
    # Both render paths run the existing authentic Manim/MathTex math contract.
    # A cited formula appears in the video ONLY as an actual teacher-authored
    # source stage action; no synthetic subtitle or postprocessing overlay.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="classroom-memory-") as tmp:
        movie = Path(tmp) / "memory.mp4"
        manifest = Path(tmp) / "render.json"
        if adaptive:
            from .adaptive_classroom_flow import render_adaptive_flow
            underlying = render_adaptive_flow(
                Path(input_file).parent / "adaptive_layout.json",
                output_mp4=movie, output_json=manifest, fps=fps,
            )
        else:
            underlying = render_flow(
                memory.flow_file, output_mp4=movie,
                output_json=manifest, fps=fps,
            )
        expected = [
            x["global_event_id"] for x in plan["events"]
        ]
        if [x["global_event_id"] for x in underlying["event_timing"]] != expected:
            raise LongboardError("MEMORY_VIDEO_EVENT_TIMELINE_MUTATION")
        output_mp4, output_json = Path(output_mp4), Path(output_json)
        output_mp4.parent.mkdir(parents=True, exist_ok=True)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        report = {
            **underlying,
            "mode": "verified_classroom_memory",
            "memory": _memory_audit(memory),
            "memory_contract_validated": True,
            "cross_stage_memory_strategy": plan["cross_stage_memory_strategy"],
            "event_memory_timing": [{
                "global_event_id": e["global_event_id"],
                "memory": memory.event_memory(e["stage_id"], e["event_id"]),
            } for e in plan["events"]],
            "fabricated_voice_or_subtitle_count": 0,
        }
        shutil.copyfile(movie, output_mp4)
        output_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return report
