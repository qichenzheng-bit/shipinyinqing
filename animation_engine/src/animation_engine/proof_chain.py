"""V2.5.3: a source-verified long-proof dependency and page-carry contract.

The engine NEVER proves an assertion or silently derives the next formula.
Each mathematical line and all proof citations come from teacher-reviewed
source. This validator guarantees ordered, complete proof references, case
coverage and safe cross-page continuity; independent math checks belong to
the author/test fixture, not to a renderer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .longboard_plan import LongboardError, _sources
from .planner import build_execution_plan


_ROLES = frozenset({
    "setup", "derivation", "lemma", "case", "merge", "conclusion"
})


@dataclass(frozen=True)
class ProofStage:
    event_id: str
    role: str
    output_ids: tuple[str, ...]
    cites: tuple[str, ...]
    carry_ids: tuple[str, ...]
    safe_break_after: bool
    case_group: str | None
    case_id: str | None


@dataclass(frozen=True)
class ProofContract:
    condition_id: str
    goal_id: str
    stages: tuple[ProofStage, ...]
    branch_groups: tuple[dict, ...]

    def for_event(self, event_id: str) -> ProofStage:
        for stage in self.stages:
            if stage.event_id == event_id:
                return stage
        raise LongboardError("PROOF_UNKNOWN_EVENT: " + event_id)

    def carry_at(self, event_id: str, written: set[str]) -> list[str]:
        stage = self.for_event(event_id)
        if any(mid not in written for mid in stage.carry_ids):
            raise LongboardError("PROOF_PREMATURE_CARRY: " + event_id)
        return list(stage.carry_ids)

    def is_safe_page_boundary(self, preceding_event: str) -> bool:
        return self.for_event(preceding_event).safe_break_after

    def event_info(self, event_id: str) -> dict:
        s = self.for_event(event_id)
        return {
            "proof_stage": s.role,
            "proof_cites": list(s.cites),
            "proof_case_group": s.case_group,
            "proof_case_id": s.case_id,
            "safe_break_after": s.safe_break_after,
        }

    def as_manifest(self) -> dict:
        return {
            "mode": "verified_proof_chain",
            "condition_object_id": self.condition_id,
            "goal_object_id": self.goal_id,
            "stage_count": len(self.stages),
            "ordered_event_ids": [s.event_id for s in self.stages],
            "branch_groups": [dict(g) for g in self.branch_groups],
            "reference_order_verified": True,
            "case_coverage_verified": True,
            "mathematical_truth_status": "teacher_reviewed_not_formally_proven",
        }


def _ids(items: Any, *, label: str, allow_empty: bool = False) -> tuple[str, ...]:
    if (not isinstance(items, list)
            or (not allow_empty and not items)
            or any(type(x) is not str or not x for x in items)
            or len(set(items)) != len(items)):
        raise LongboardError("PROOF_BAD_" + label)
    return tuple(items)


def checked_proof_chain(payload, storyboard, execution) -> ProofContract:
    """Reject unknown, premature, branched or unsafely pageable proof sources."""
    from visual_director.models import StoryboardPlan
    from .models import ExecutionPlan

    board = StoryboardPlan.model_validate(storyboard)
    plan = ExecutionPlan.model_validate(execution)
    if plan.model_dump(mode="json") != build_execution_plan(board).model_dump(mode="json"):
        raise LongboardError("PROOF_EXECUTION_SOURCE_MISMATCH")
    required = {
        "schema_version", "mode", "teacher_reviewed",
        "source_storyboard_sha256", "anchors", "stages", "branch_groups",
    }
    if (not isinstance(payload, dict) or set(payload) != required
            or payload.get("schema_version") != "1.0"
            or payload.get("mode") != "verified_proof_chain"
            or payload.get("teacher_reviewed") is not True):
        raise LongboardError("PROOF_INVALID_MANIFEST")
    if payload["source_storyboard_sha256"] != plan.source_storyboard_sha256:
        raise LongboardError("PROOF_SOURCE_HASH")
    anchors = payload["anchors"]
    if (not isinstance(anchors, dict)
            or set(anchors) != {"condition_object_id", "goal_object_id"}):
        raise LongboardError("PROOF_ANCHOR_FIELDS")
    condition, goal = anchors["condition_object_id"], anchors["goal_object_id"]
    if type(condition) is not str or type(goal) is not str or not condition or not goal or condition == goal:
        raise LongboardError("PROOF_BAD_ANCHORS")
    sources = _sources(plan)
    events = [scene.event_id for scene in board.scenes]
    if len(events) < 4 or len(events) != len(set(events)):
        raise LongboardError("PROOF_BAD_EVENTS")
    outputs = {}
    for event in plan.scenes:
        outputs[event.event_id] = [
            action.object_id for action in event.actions
            if action.kind in ("progressive_write", "restore")
            and action.to_region != "question"
            and action.object_id in sources
        ]
    if (condition not in outputs[events[0]]
            or goal not in outputs[events[0]]):
        raise LongboardError("PROOF_ANCHORS_MUST_BE_INITIAL")
    raw_stages = payload["stages"]
    if (not isinstance(raw_stages, list)
            or len(raw_stages) != len(events) or len(raw_stages) > 45):
        raise LongboardError("PROOF_STAGE_COVERAGE")
    seen: set[str] = set()
    owner_case: dict[str, tuple[str, str]] = {}
    stages: list[ProofStage] = []
    stage_fields = {
        "event_id", "role", "output_ids", "cites", "carry_ids",
        "safe_break_after", "case_group", "case_id",
    }
    for index, raw in enumerate(raw_stages):
        if not isinstance(raw, dict) or set(raw) != stage_fields:
            raise LongboardError("PROOF_STAGE_FIELDS")
        event_id = raw["event_id"]
        if event_id != events[index] or raw["role"] not in _ROLES:
            raise LongboardError("PROOF_STAGE_ORDER")
        own = _ids(raw["output_ids"], label="OUTPUTS")
        cites = _ids(raw["cites"], label="CITES", allow_empty=index == 0)
        carries = _ids(raw["carry_ids"], label="CARRY", allow_empty=index == 0)
        if list(own) != outputs[event_id] or any(x in seen for x in own):
            raise LongboardError("PROOF_SOURCE_OUTPUT_MISMATCH")
        if any(mid not in seen for mid in cites):
            raise LongboardError("PROOF_PREMATURE_REFERENCE: " + event_id)
        if any(mid not in seen for mid in carries):
            raise LongboardError("PROOF_PREMATURE_CARRY: " + event_id)
        if (index > 0 and
                (condition not in carries or goal not in carries
                 or any(mid not in carries for mid in cites))):
            raise LongboardError("PROOF_REQUIRED_CONTEXT_MISSING: " + event_id)
        if type(raw["safe_break_after"]) is not bool:
            raise LongboardError("PROOF_BAD_SAFE_BREAK")
        group, case = raw["case_group"], raw["case_id"]
        if raw["role"] == "case":
            if (not isinstance(group, str) or not group
                    or not isinstance(case, str) or not case):
                raise LongboardError("PROOF_BAD_CASE_LABEL")
            for mid in cites:
                if mid in owner_case and owner_case[mid] != (group, case):
                    raise LongboardError("PROOF_CASE_CROSS_REFERENCE")
            for mid in own:
                owner_case[mid] = (group, case)
        elif group is not None or case is not None:
            raise LongboardError("PROOF_CASE_LABEL_ON_NONCASE")
        if index == 0 and (raw["role"] != "setup" or cites or carries):
            raise LongboardError("PROOF_INITIAL_STAGE")
        if index == len(raw_stages)-1:
            if raw["role"] != "conclusion" or raw["safe_break_after"]:
                raise LongboardError("PROOF_FINAL_STAGE")
            if not any(mid not in (condition, goal) for mid in cites):
                raise LongboardError("PROOF_FINAL_WITHOUT_DERIVATION")
        stages.append(ProofStage(
            event_id, raw["role"], own, cites, carries,
            raw["safe_break_after"], group, case
        ))
        seen.update(own)
    if any(mid not in seen for mid in sources):
        raise LongboardError("PROOF_UNDECLARED_SOURCE_MATH")
    branch_groups = payload["branch_groups"]
    if not isinstance(branch_groups, list):
        raise LongboardError("PROOF_BAD_BRANCH_GROUPS")
    seen_groups = set()
    verified_groups = []
    for group in branch_groups:
        if (not isinstance(group, dict)
                or set(group) != {"group_id", "cases", "merge_event_id"}):
            raise LongboardError("PROOF_BRANCH_GROUP_FIELDS")
        gid = group["group_id"]
        if type(gid) is not str or not gid or gid in seen_groups:
            raise LongboardError("PROOF_DUPLICATE_BRANCH_GROUP")
        seen_groups.add(gid)
        cases = _ids(group["cases"], label="BRANCH_CASES")
        if len(cases) < 2:
            raise LongboardError("PROOF_BRANCH_NEEDS_MULTIPLE_CASES")
        actual = [stage.case_id for stage in stages if stage.case_group == gid]
        if actual != list(cases):
            raise LongboardError("PROOF_MISSING_OR_EXTRA_CASES")
        merge = next((stage for stage in stages
                      if stage.event_id == group["merge_event_id"]), None)
        if merge is None or merge.role != "merge":
            raise LongboardError("PROOF_MISSING_BRANCH_MERGE")
        case_stages = [s for s in stages if s.case_group == gid]
        if any(stages.index(s) >= stages.index(merge) for s in case_stages):
            raise LongboardError("PROOF_MERGE_BEFORE_CASE")
        # All case conclusions must be explicitly cited to justify a merge.
        case_outputs = [stage.output_ids[-1] for stage in case_stages]
        if any(mid not in merge.cites for mid in case_outputs):
            raise LongboardError("PROOF_INCOMPLETE_BRANCH_MERGE")
        verified_groups.append({
            "group_id": gid, "cases": list(cases),
            "merge_event_id": merge.event_id,
        })
    declared_groups = {s.case_group for s in stages if s.case_group}
    if declared_groups != seen_groups:
        raise LongboardError("PROOF_UNDECLARED_BRANCH_GROUP")
    for stage in stages:
        if stage.role == "merge" and stage.event_id not in {
                group["merge_event_id"] for group in verified_groups}:
            raise LongboardError("PROOF_UNDECLARED_BRANCH_MERGE")
        if stage.role not in ("case", "merge", "conclusion"):
            if any(mid in owner_case for mid in stage.cites):
                raise LongboardError("PROOF_UNMERGED_CASE_REFERENCE")
    return ProofContract(condition, goal, tuple(stages), tuple(verified_groups))
