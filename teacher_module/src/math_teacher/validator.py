"""Deterministic provenance, reference, sequencing and integrity verification."""
from __future__ import annotations
from .models import (
    TeacherInput, Understanding, TeachingPlan, LessonDraft, SubtitleCandidate,
    ValidationIssue, ValidationReport, MathVerification,
)
from .verifier import verify_math_check


class Collector:
    def __init__(self):
        self.issues: list[ValidationIssue] = []

    def add(self, stage: str, code: str, detail: str, severity: str = "error"):
        self.issues.append(ValidationIssue(stage=stage, code=code, detail=detail, severity=severity))

    def unique(self, ids: list[str], stage: str, code: str):
        if any(not i.strip() for i in ids) or len(set(ids)) != len(ids):
            self.add(stage, code, "IDs must be unique and nonblank")


def check_input_sources(source: TeacherInput, c: Collector) -> None:
    """Ensure segmented transcriptions exactly cover original text, in order.

    Boundary whitespace is permitted; mathematical tokens, punctuation and
    internal spaces must be preserved. This is source-integrity checking, not
    a claim that model-extracted mathematical statements are semantically true.
    """
    for kind, original, segments in (
        ("problem", source.problem, source.problem_segments),
        ("solution", source.reference_solution, source.solution_segments),
    ):
        cursor = 0
        for segment in segments:
            if segment.kind != kind:
                c.add("input", "SOURCE_KIND", f"{segment.source_id}: expected {kind}")
            if not segment.text.strip():
                c.add("input", "SOURCE_TEXT_MISMATCH", f"{segment.source_id}: empty source segment")
                break
            start = original.find(segment.text, cursor)
            if start == -1 or original[cursor:start].strip():
                c.add("input", "SOURCE_TEXT_MISMATCH", f"{segment.source_id}: source text differs from the original {kind}")
                break
            cursor = start + len(segment.text)
        else:
            if original[cursor:].strip():
                c.add("input", "SOURCE_TEXT_MISMATCH", f"{kind}: source segments omit trailing original content")


def check_understanding(source: TeacherInput, a: Understanding, c: Collector) -> list[MathVerification]:
    stage = "A"
    if not a.solution_steps:
        c.add(stage, "NO_STEPS", "Reference analysis contains no steps")
    steps = {x.step_id: x for x in a.solution_steps}
    c.unique([x.step_id for x in a.solution_steps], stage, "DUPLICATE_STEP_ID")
    known_sources = {x.source_id: x.kind for x in source.problem_segments + source.solution_segments}
    c.unique(list(known_sources), stage, "DUPLICATE_SOURCE_ID")
    for x in source.problem_segments:
        if x.kind != "problem":
            c.add(stage, "SOURCE_KIND", f"{x.source_id} is not a problem segment")
    for x in source.solution_segments:
        if x.kind != "solution":
            c.add(stage, "SOURCE_KIND", f"{x.source_id} is not a solution segment")
    visited = set()
    covered_solutions: set[str] = set()
    solution_positions = {x.source_id: i for i, x in enumerate(source.solution_segments)}
    solution_texts = {x.source_id: x.text for x in source.solution_segments}
    previous_source_position = -1
    previous_quote_position = (-1, -1)
    for x in a.solution_steps:
        if not x.source_refs:
            c.add(stage, "MISSING_SOURCE", f"{x.step_id}: empty source_refs")
        for ref in x.source_refs:
            if ref not in known_sources:
                c.add(stage, "UNKNOWN_SOURCE", f"{x.step_id}: source ref {ref} does not exist")
            if x.origin == "source" and known_sources.get(ref) == "solution":
                covered_solutions.add(ref)
        if x.origin == "source" and not any(known_sources.get(ref) == "solution" for ref in x.source_refs):
            c.add(stage, "STEP_WITHOUT_SOLUTION_SOURCE", x.step_id)
        if x.origin == "source":
            positions = [solution_positions[ref] for ref in x.source_refs if ref in solution_positions]
            if positions:
                if min(positions) < previous_source_position or positions != sorted(positions):
                    c.add(stage, "SOURCE_STEP_ORDER", f"{x.step_id}: solution segment references are out of order")
                previous_source_position = max(previous_source_position, max(positions))
            for ref in x.source_refs:
                if ref not in solution_texts:
                    continue
                quote = x.source_quotes.get(ref, "")
                if not quote.strip():
                    c.add(stage, "SOURCE_QUOTE_REQUIRED",
                          f"{x.step_id}: missing literal quotation for {ref}")
                    continue
                text = solution_texts[ref]
                first_offset = text.find(quote)
                if first_offset < 0:
                    c.add(stage, "SOURCE_QUOTE_MISMATCH",
                          f"{x.step_id}: quotation does not occur in {ref}")
                    continue
                source_index = solution_positions[ref]
                # Repeated literal phrases must use a later occurrence where one exists.
                start = previous_quote_position[1] + 1 if previous_quote_position[0] == source_index else 0
                offset = text.find(quote, start)
                if offset < 0:
                    c.add(stage, "SOURCE_STEP_ORDER",
                          f"{x.step_id}: no later occurrence of quotation in {ref}")
                    continue
                previous_quote_position = (source_index, offset)
            if set(x.source_quotes) - set(x.source_refs):
                c.add(stage, "SOURCE_QUOTE_REFERENCE",
                      f"{x.step_id}: quotation cites a segment not referenced by this step")
        if x.origin == "organizational" and x.relation_type in {
            "equals", "asymptotic", "limit", "implies", "iff", "other"
        } and (x.input_expressions or x.output_expressions):
            c.add(stage, "ORGANIZATIONAL_ASSERTION_REQUIRES_REVIEW",
                  f"{x.step_id}: mathematical claims cannot bypass derived-step verification", "review")
        if x.origin != "source" and not x.justification.strip():
            c.add(stage, "UNJUSTIFIED_ADDITION", x.step_id)
        if x.origin == "organizational" and not x.operation.strip():
            c.add(stage, "UNEXPLAINED_ORGANIZATION", x.step_id)
        if x.verification_status not in ("pending_check", "source_only"):
            c.add(stage, "INVALID_VERIFICATION", x.step_id)
        for dep in x.depends_on:
            if dep not in steps or dep == x.step_id:
                c.add(stage, "INVALID_DEPENDENCY", f"{x.step_id} depends on {dep}")
            elif dep not in visited:
                c.add(stage, "FORWARD_DEPENDENCY", f"{x.step_id} depends on future step {dep}")
        visited.add(x.step_id)
    for seg in source.solution_segments:
        if seg.source_id not in covered_solutions:
            c.add(stage, "UNCOVERED_SOLUTION_SOURCE", seg.source_id)

    c.unique([x.check_id for x in a.check_requests], stage, "DUPLICATE_CHECK_ID")
    verifications = []
    bound_verified_step_ids: set[str] = set()
    for req in a.check_requests:
        if req.step_id not in steps:
            c.add(stage, "CHECK_UNKNOWN_STEP", req.step_id)
            continue
        result = verify_math_check(req)
        verifications.append(result)
        step = steps[req.step_id]
        # An unrelated identity may be true but cannot certify this step.
        inputs = {_math_key(expr) for expr in step.input_expressions}
        outputs = {_math_key(expr) for expr in step.output_expressions}
        lhs, rhs = _math_key(req.lhs_expr), _math_key(req.rhs_expr)
        bound = (lhs in inputs and rhs in outputs) or (rhs in inputs and lhs in outputs)
        if not bound:
            c.add(stage, "MATH_CHECK_UNBOUND", f"{req.check_id}: expressions do not match {req.step_id}", "review")
        if req.conditions:
            c.add(stage, "MATH_CHECK_CONDITIONS_UNVERIFIED",
                  f"{req.check_id}: conditional identity needs separate verification", "review")
        if result.status == "verified" and bound and not req.conditions and step.relation_type == "equals":
            bound_verified_step_ids.add(req.step_id)
        if result.status == "failed":
            c.add(stage, "MATH_CHECK_FAILED", f"{req.step_id}: {result.explanation}")
        if result.status == "undetermined":
            c.add(stage, "MATH_UNDETERMINED", f"{req.step_id}: {result.explanation}", "review")
    for step in a.solution_steps:
        if step.origin == "derived" and step.step_id not in bound_verified_step_ids:
            c.add(stage, "ADDED_STEP_REQUIRES_REVIEW", step.step_id, "review")
    for issue in a.issues:
        for ref in issue.source_refs:
            if ref not in known_sources:
                c.add(stage, "UNKNOWN_ISSUE_SOURCE", ref)
        c.add(stage, issue.code, issue.description, "review" if not issue.critical else "error")
    if a.review_status == "blocked":
        c.add(stage, "MODEL_REPORTED_BLOCKED", "A found blocked reference analysis")
    if a.review_status == "needs_confirmation":
        c.add(stage, "MODEL_REPORTED_REVIEW", "A requests confirmation", "review")
    return verifications


def check_plan(a: Understanding, b: TeachingPlan, c: Collector) -> None:
    stage = "B"
    steps = {x.step_id for x in a.solution_steps}
    bindings = {x.knowledge_id: x for x in b.knowledge_bindings}
    events = {x.event_id: x for x in b.teaching_events}
    c.unique(list(x.knowledge_id for x in b.knowledge_bindings), stage, "DUPLICATE_KNOWLEDGE_ID")
    c.unique(list(x.event_id for x in b.teaching_events), stage, "DUPLICATE_EVENT_ID")
    if not b.teaching_events:
        c.add(stage, "NO_TEACHING_EVENTS", "Teaching plan has no events")
    if not b.teaching_events or b.teaching_events[0].event_type != "read_question":
        c.add(stage, "NO_QUESTION_OPENING", "First teaching event should read the actual question")
    for item in b.knowledge_bindings:
        if not item.source_step_ids or item.return_to_step_id not in item.source_step_ids:
            c.add(stage, "UNBOUND_KNOWLEDGE", item.knowledge_id)
        for sid in item.source_step_ids:
            if sid not in steps:
                c.add(stage, "KNOWLEDGE_UNKNOWN_STEP", f"{item.knowledge_id}: {sid}")
        if not item.teaching_reason.strip() or not item.formula_or_theorem.strip():
            c.add(stage, "EMPTY_KNOWLEDGE", item.knowledge_id)
        if not item.applicability_conditions or any(not cond.strip() for cond in item.applicability_conditions):
            c.add(stage, "KNOWLEDGE_MISSING_CONDITIONS", f"{item.knowledge_id}: explicitly state conditions, or that no extra conditions apply")
        if not item.application_mapping or any(not key.strip() or not value.strip() for key, value in item.application_mapping.items()):
            c.add(stage, "KNOWLEDGE_MISSING_APPLICATION", f"{item.knowledge_id}: map the knowledge to actual problem objects or conditions")
    coverage = {step: [] for step in steps}
    for event in b.teaching_events:
        for sid in event.source_step_ids:
            if sid not in steps:
                c.add(stage, "EVENT_UNKNOWN_STEP", f"{event.event_id}: {sid}")
            else:
                coverage[sid].append(event.event_id)
        for kid in event.knowledge_binding_ids:
            if kid not in bindings:
                c.add(stage, "EVENT_UNKNOWN_KNOWLEDGE", f"{event.event_id}: {kid}")
    for sid in steps:
        if not coverage[sid]:
            c.add(stage, "UNCOVERED_STEP", sid)
        if set(coverage[sid]) != set(b.reference_step_coverage.get(sid, [])):
            c.add(stage, "COVERAGE_MISMATCH", f"{sid}: coverage map must match event references")
    for sid in b.reference_step_coverage:
        if sid not in steps:
            c.add(stage, "COVERAGE_UNKNOWN_STEP", sid)
    # Knowledge -> application -> source derivation/proof, respecting the actual reference step.
    for kid, binding in bindings.items():
        ki = [i for i, e in enumerate(b.teaching_events) if e.event_type == "knowledge" and kid in e.knowledge_binding_ids]
        ai = [i for i, e in enumerate(b.teaching_events) if e.event_type == "application" and kid in e.knowledge_binding_ids]
        ri = [i for i, e in enumerate(b.teaching_events) if e.event_type in ("derivation", "proof", "branch", "subgoal") and binding.return_to_step_id in e.source_step_ids]
        if not ki or not ai or not ri or not min(ki) < min(ai) < min(ri):
            c.add(stage, "INVALID_KNOWLEDGE_SEQUENCE", f"{kid}: need knowledge -> application -> reference derivation/proof")
    for request in b.supplement_requests:
        if any(s not in steps for s in request.source_step_ids):
            c.add(stage, "SUPPLEMENT_UNKNOWN_SOURCE", request.reason)
        c.add(stage, "UNVALIDATED_SUPPLEMENT_REQUEST", request.reason, "review")
    for issue in b.planning_issues:
        c.add(stage, "PLANNING_ISSUE", issue, "review")


def _math_key(expr: str) -> str:
    """Small, deliberately bounded notation bridge; never asserts equivalence."""
    import re
    text = expr.strip().strip("$")
    text = "".join(text.split())
    # The verifier consumes Python-style arithmetic, while classroom MathTex
    # uses ^ and often omits multiplication between adjacent parentheses.
    text = re.sub(r"\^\{([0-8])\}", r"**\1", text)
    text = re.sub(r"\^([0-8])", r"**\1", text)
    text = text.replace(")(", ")*(")
    return text


def check_lesson(a: Understanding, b: TeachingPlan, d: LessonDraft, c: Collector,
                 source: TeacherInput | None = None) -> list[SubtitleCandidate]:
    stage = "C"
    plan = {x.event_id: x for x in b.teaching_events}
    steps = {x.step_id: x for x in a.solution_steps}
    bindings = {x.knowledge_id: x for x in b.knowledge_bindings}
    actual_events = {x.event_id: x for x in d.lesson_events}
    units = {x.speech_unit_id: x for x in d.speech_units}
    boards = {x.board_action_id: x for x in d.board_actions}
    objects = {x.math_object_id: x for x in d.math_objects}
    anims = {x.animation_id: x for x in d.animation_intents}
    for label, arr in (("EVENT", d.lesson_events), ("SPEECH", d.speech_units), ("BOARD", d.board_actions), ("MATH_OBJECT", d.math_objects), ("ANIMATION", d.animation_intents)):
        field = {"EVENT":"event_id", "SPEECH":"speech_unit_id", "BOARD":"board_action_id", "MATH_OBJECT":"math_object_id", "ANIMATION":"animation_id"}[label]
        c.unique([getattr(x, field) for x in arr], stage, f"DUPLICATE_{label}_ID")
    if list(x.event_id for x in d.lesson_events) != list(plan):
        c.add(stage, "EVENT_ORDER_MISMATCH", "C must preserve teaching plan event order and IDs")
    plan_steps = set(s for x in b.teaching_events for s in x.source_step_ids)
    for obj in d.math_objects:
        if not obj.latex.strip() or not obj.source_step_ids or any(s not in plan_steps for s in obj.source_step_ids):
            c.add(stage, "INVALID_MATH_OBJECT", obj.math_object_id)
    expected_speech_order = [uid for e in d.lesson_events for uid in e.speech_unit_ids]
    actual_speech_order = [u.speech_unit_id for u in d.speech_units]
    if expected_speech_order != actual_speech_order:
        c.add(stage, "SPEECH_ORDER_MISMATCH", "Speech units must follow event and per-event order")
    for e in d.lesson_events:
        for category, ids in (("speech", e.speech_unit_ids), ("board", e.board_action_ids),
                              ("animation", e.animation_intent_ids)):
            if len(ids) != len(set(ids)):
                c.add(stage, "DUPLICATE_EVENT_MEMBER", f"{e.event_id}: duplicate {category} membership")
        p = plan.get(e.event_id)
        if p is None:
            c.add(stage, "UNKNOWN_LESSON_EVENT", e.event_id)
            continue
        if e.source_step_ids != p.source_step_ids or e.knowledge_binding_ids != p.knowledge_binding_ids:
            c.add(stage, "EVENT_CHANGED_SEMANTICS", e.event_id)
        for kind, ids, lookup in (("speech", e.speech_unit_ids, units), ("board", e.board_action_ids, boards), ("animation", e.animation_intent_ids, anims)):
            for ref in ids:
                if ref not in lookup:
                    c.add(stage, "UNRESOLVED_EVENT_REFERENCE", f"{e.event_id} -> {kind}:{ref}")
                elif lookup[ref].event_id != e.event_id:
                    c.add(stage, "CROSS_EVENT_REFERENCE", f"{e.event_id} -> {kind}:{ref}")
        if not e.speech_unit_ids:
            c.add(stage, "SILENT_TEACHING_EVENT", e.event_id)
        if p.intended_board_content and not e.board_action_ids:
            c.add(stage, "MISSING_BOARD_FOR_PLAN", e.event_id)
    # Full natural-language reading cannot be decided by token matching.
    # A clearly unrelated opening is flagged only as a non-blocking warning.
    if source is not None and d.lesson_events:
        opening = d.lesson_events[0]
        read_units = [units[uid] for uid in opening.speech_unit_ids if uid in units]
        spoken = " ".join(part.value for unit in read_units for part in unit.parts)
        question = source.problem
        import re
        question_commands = set(re.findall(r"\\[A-Za-z]+", question))
        spoken_commands = set(re.findall(r"\\[A-Za-z]+", spoken))
        meaningful_math = bool(question_commands & spoken_commands)
        meaningful_text = any(token in spoken for token in ("题目", "求", "已知", "条件", "证明", "设"))
        if not meaningful_math and not meaningful_text:
            c.add(stage, "READ_QUESTION_ANCHOR_WEAK",
                  "Opening speech has no clear question cue; confirm actual question coverage", "warning")
    for unit in d.speech_units:
        if unit.event_id not in actual_events or unit.speech_unit_id not in actual_events[unit.event_id].speech_unit_ids:
            c.add(stage, "ORPHAN_SPEECH", unit.speech_unit_id)
        if not unit.parts or any(not part.value.strip() for part in unit.parts):
            c.add(stage, "EMPTY_SPEECH", unit.speech_unit_id)
    for ba in d.board_actions:
        if ba.event_id not in actual_events or ba.board_action_id not in actual_events[ba.event_id].board_action_ids:
            c.add(stage, "ORPHAN_BOARD", ba.board_action_id)
        if ba.speech_unit_id not in units or units[ba.speech_unit_id].event_id != ba.event_id:
            c.add(stage, "UNSYNCED_BOARD", ba.board_action_id)
        if ba.math_object_id not in objects:
            c.add(stage, "BOARD_UNKNOWN_OBJECT", ba.board_action_id)
        if not ba.semantic_reason.strip():
            c.add(stage, "DECORATIVE_BOARD", ba.board_action_id)
        obj = objects.get(ba.math_object_id)
        planned = plan.get(ba.event_id)
        if obj is not None and planned is not None and ba.action in ("write", "transform", "substitute", "group"):
            if not obj.source_step_ids or not set(obj.source_step_ids) <= set(planned.source_step_ids):
                c.add(stage, "BOARD_STEP_CONTEXT_MISMATCH",
                      f"{ba.board_action_id}: board content must cite current event source steps")
            # Speech and board are generated together in stage C; they cannot
            # independently certify one another's mathematics. Require a
            # verified upstream step/knowledge anchor, or request review.
            spoken_anchors: set[str] = set()
            upstream_anchors: set[str] = set()
            unit = units.get(ba.speech_unit_id)
            if unit is not None and unit.event_id == ba.event_id:
                spoken_anchors.update(_math_key(part.value) for part in unit.parts if part.kind == "math")
            for sid in planned.source_step_ids:
                step = steps.get(sid)
                if step is not None:
                    upstream_anchors.update(
                        _math_key(expr) for expr in step.input_expressions + step.output_expressions
                    )
            for kid in planned.knowledge_binding_ids:
                binding = bindings.get(kid)
                if binding is not None:
                    upstream_anchors.add(_math_key(binding.formula_or_theorem))
                    upstream_anchors.update(_math_key(v) for v in binding.application_mapping.values())
            math_key = _math_key(obj.latex)
            if math_key not in upstream_anchors:
                if math_key in spoken_anchors:
                    c.add(stage, "BOARD_SPEECH_ONLY_MATH",
                          f"{ba.board_action_id}: spoken formula is not anchored in the validated teaching plan",
                          "review")
                else:
                    c.add(stage, "BOARD_UNRELATED_TO_CONTEXT",
                          f"{ba.board_action_id}: board formula has no speech, reference-step or knowledge anchor")
    for a in d.animation_intents:
        if a.event_id not in actual_events or a.animation_id not in actual_events[a.event_id].animation_intent_ids:
            c.add(stage, "ORPHAN_ANIMATION", a.animation_id)
        if not a.mathematical_goal.strip():
            c.add(stage, "DECORATIVE_ANIMATION", a.animation_id)
        for ref in a.board_action_ids:
            if ref not in boards or boards[ref].event_id != a.event_id:
                c.add(stage, "ANIMATION_UNKNOWN_BOARD", f"{a.animation_id}: {ref}")
        for ref in a.speech_unit_ids:
            if ref not in units or units[ref].event_id != a.event_id:
                c.add(stage, "ANIMATION_UNKNOWN_SPEECH", f"{a.animation_id}: {ref}")
    for issue in d.consistency_issues:
        c.add(stage, "CONSISTENCY_ISSUE", issue, "review")
    # Subtitles are projected from speech content only. No second AI subtitle writing.
    return [SubtitleCandidate(subtitle_id="subtitle:"+u.speech_unit_id, speech_unit_id=u.speech_unit_id, parts=u.parts) for u in d.speech_units]


def compile_report(c: Collector, math_checks: list[MathVerification]) -> ValidationReport:
    kinds = {issue.severity for issue in c.issues}
    status = "blocked" if "error" in kinds else "needs_review" if "review" in kinds else "ready_with_limits"
    return ValidationReport(issues=c.issues, math_checks=math_checks, status=status)
