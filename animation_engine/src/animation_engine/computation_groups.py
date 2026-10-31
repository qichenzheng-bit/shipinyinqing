"""V2.5.1: reviewed multi-part mathematics contract and result ledger.

This module stores *relationships* between verified original formula objects;
it does not split an integral, calculate an answer or synthesize MathTex. Every
part is a complete subproblem, potentially containing multiple logically
indivisible teacher events. Only declared safe boundaries permit intra-part
page breaks. Missing/early results and unrendered teacher events fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .longboard_plan import LongboardError, _sources
from .models import ExecutionPlan
from visual_director.models import StoryboardPlan


@dataclass(frozen=True)
class Part:
    id: str
    event_ids: tuple[str, ...]
    result_id: str
    safe_break_after: tuple[str, ...]
    checkpoints: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ComputationGroups:
    decomposition_event_id: str
    decomposition_object_id: str
    parts: tuple[Part, ...]
    final_event_id: str
    final_object_id: str
    source_storyboard_sha256: str

    @property
    def owner_by_event(self) -> dict[str, str]:
        return {event: part.id for part in self.parts for event in part.event_ids}

    def carry_at(self, event_id: str, written: set[str]) -> list[str]:
        """Only verified *already written* source mathematics may be carried."""
        keep = []
        if self.decomposition_object_id in written:
            keep.append(self.decomposition_object_id)
        for part in self.parts:
            if part.result_id in written:
                keep.append(part.result_id)
            elif event_id in part.event_ids:
                # A multi-event integral may continue on a fresh blackboard.
                # Use only a checkpoint that was actually written already.
                for prior_event, mid in part.checkpoints:
                    if mid in written:
                        keep.append(mid)
        return list(dict.fromkeys(keep))

    def is_safe_page_boundary(self, previous_event: str, next_event: str) -> bool:
        owners=self.owner_by_event
        if owners.get(previous_event)!=owners.get(next_event):
            return True
        owner=owners.get(previous_event)
        if owner is None:
            return True
        part=next(p for p in self.parts if p.id==owner)
        return previous_event in part.safe_break_after

    def event_info(self, event_id: str) -> dict:
        owner=self.owner_by_event.get(event_id)
        kind=("decomposition" if event_id==self.decomposition_event_id
              else "final" if event_id==self.final_event_id
              else "subproblem")
        return {"computation_role":kind,"subproblem_id":owner,
                "semantic_group":"computation:"+(
                    owner if owner is not None else kind)}

    def as_manifest(self) -> dict:
        return {
            "mode":"multi_part_computation",
            "decomposition_object_id":self.decomposition_object_id,
            "part_count":len(self.parts),
            "ordered_parts":[{
                "part_id":p.id,
                "event_ids":list(p.event_ids),
                "result_object_id":p.result_id,
                "safe_break_after":list(p.safe_break_after),
                "checkpoints":[{"event_id":eid,"object_id":mid}
                               for eid,mid in p.checkpoints],
            } for p in self.parts],
            "final_object_id":self.final_object_id,
        }


def checked_computation_groups(
        payload: dict[str,Any], storyboard: StoryboardPlan,
        execution: ExecutionPlan) -> ComputationGroups:
    """Strict source-ordered contract, not a permissive decoration layer."""
    board=StoryboardPlan.model_validate(storyboard)
    plan=ExecutionPlan.model_validate(execution)
    if not isinstance(payload,dict) or set(payload)!={
        "schema_version","mode","source_storyboard_sha256",
        "teacher_reviewed","decomposition","parts","final"
    } or payload["schema_version"]!="1.0" or payload["mode"]!="multi_part_computation":
        raise LongboardError("COMPUTATION_GROUPS_INVALID_SCHEMA")
    if payload["teacher_reviewed"] is not True:
        raise LongboardError("COMPUTATION_GROUPS_NEED_TEACHER_REVIEW")
    if payload["source_storyboard_sha256"]!=plan.source_storyboard_sha256:
        raise LongboardError("COMPUTATION_GROUPS_SOURCE_HASH")
    if not isinstance(payload["decomposition"],dict) or set(payload["decomposition"])!={
        "event_id","object_id"
    }:
        raise LongboardError("COMPUTATION_DECOMPOSITION_FIELDS")
    if not isinstance(payload["final"],dict) or set(payload["final"])!={
        "event_id","object_id"
    }:
        raise LongboardError("COMPUTATION_FINAL_FIELDS")
    evorder=[s.event_id for s in board.scenes]
    if evorder != [s.event_id for s in plan.scenes] or len(evorder)!=len(set(evorder)):
        raise LongboardError("COMPUTATION_EVENT_SOURCE_MISMATCH")
    positions={eid:i for i,eid in enumerate(evorder)}
    written_by_event={
        sc.event_id:tuple(a.object_id for a in sc.actions
                          if a.kind in ("progressive_write","restore")
                          and a.to_region!="question")
        for sc in plan.scenes
    }
    all_writes=[mid for ids in written_by_event.values() for mid in ids]
    if len(all_writes)!=len(set(all_writes)):
        raise LongboardError("COMPUTATION_DUPLICATE_SOURCE_WRITE")
    sources=_sources(plan)
    decomp=payload["decomposition"]
    final=payload["final"]
    if not evorder or decomp["event_id"]!=evorder[0] or final["event_id"]!=evorder[-1]:
        raise LongboardError("COMPUTATION_EVENT_BOUNDARY_ORDER")
    def check_write(event_id,object_id):
        if (event_id not in positions or object_id not in sources
                or object_id not in written_by_event[event_id]):
            raise LongboardError("COMPUTATION_UNKNOWN_SOURCE_OBJECT: "+str(object_id))
    check_write(decomp["event_id"],decomp["object_id"])
    check_write(final["event_id"],final["object_id"])
    raw_parts=payload["parts"]
    if not isinstance(raw_parts,list) or not 2<=len(raw_parts)<=20:
        raise LongboardError("COMPUTATION_PART_COUNT")
    parts=[]
    assigned=[]
    part_ids=set()
    output_ids=set()
    for raw in raw_parts:
        if not isinstance(raw,dict) or set(raw)!={
            "id","event_ids","result_object_id",
            "safe_break_after","checkpoints"
        }:
            raise LongboardError("COMPUTATION_PART_FIELDS")
        ident=raw["id"]
        if (not isinstance(ident,str) or not ident.isidentifier()
                or ident in part_ids):
            raise LongboardError("COMPUTATION_DUPLICATE_PART_ID")
        part_ids.add(ident)
        group_events=raw["event_ids"]
        if (not isinstance(group_events,list) or not group_events
                or any(eid not in positions or type(eid) is not str
                       for eid in group_events)
                or len(set(group_events))!=len(group_events)):
            raise LongboardError("COMPUTATION_BAD_PART_EVENT_IDS")
        if ([positions[e] for e in group_events]!=list(range(
                positions[group_events[0]],positions[group_events[-1]]+1))):
            raise LongboardError("COMPUTATION_SPLIT_PART_OUT_OF_ORDER")
        output=raw["result_object_id"]
        if output in output_ids:
            raise LongboardError("COMPUTATION_RESULT_REUSED")
        output_ids.add(output)
        check_write(group_events[-1],output)
        # Final result must be the final *new mathematical write* in a part.
        if written_by_event[group_events[-1]][-1]!=output:
            raise LongboardError("COMPUTATION_RESULT_NOT_LAST_STEP")
        safe=raw["safe_break_after"]
        if (not isinstance(safe,list) or len(set(safe))!=len(safe)
                or any(e not in group_events[:-1] for e in safe)):
            raise LongboardError("COMPUTATION_BAD_SAFE_BREAK")
        checkpoints=raw["checkpoints"]
        if not isinstance(checkpoints,list):
            raise LongboardError("COMPUTATION_BAD_CHECKPOINTS")
        checked=[]
        for c in checkpoints:
            if (not isinstance(c,dict) or set(c)!={"event_id","object_id"}
                    or c["event_id"] not in safe):
                raise LongboardError("COMPUTATION_CHECKPOINT_FIELDS")
            check_write(c["event_id"],c["object_id"])
            # A fresh page must display the *concluded* previous subgoal,
            # not an unrelated earlier intermediate expression.
            if written_by_event[c["event_id"]][-1]!=c["object_id"]:
                raise LongboardError("COMPUTATION_CHECKPOINT_NOT_FINAL_IN_EVENT")
            checked.append((c["event_id"],c["object_id"]))
        if len(checked)!=len(safe) or len(set(e for e,_ in checked))!=len(safe):
            raise LongboardError("COMPUTATION_CHECKPOINT_COVERAGE")
        parts.append(Part(
            id=ident,event_ids=tuple(group_events),result_id=output,
            safe_break_after=tuple(safe),checkpoints=tuple(checked)
        ))
        assigned.extend(group_events)
    expected=evorder[1:-1]
    if assigned!=expected:
        raise LongboardError(
            "COMPUTATION_EVENTS_MISSING_OR_UNORDERED: expected "+repr(expected)
        )
    if (decomp["object_id"] in output_ids or final["object_id"] in output_ids
            or final["object_id"]==decomp["object_id"]):
        raise LongboardError("COMPUTATION_ROLE_MATH_REUSED")
    return ComputationGroups(
        decomposition_event_id=decomp["event_id"],
        decomposition_object_id=decomp["object_id"],
        parts=tuple(parts),
        final_event_id=final["event_id"],
        final_object_id=final["object_id"],
        source_storyboard_sha256=plan.source_storyboard_sha256,
    )
