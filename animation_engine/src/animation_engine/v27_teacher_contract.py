"""V2.7 source-bound classroom pedagogy and pre-render script inspection.

The contract verifies evidence attached to the *actual approved narration*.
It does not claim that Chinese readings are mathematically equivalent to LaTeX
or that every mathematical statement is formally true. Legacy V1 video
packages remain readable but do not receive a V2.7 acceptance label.
"""
from __future__ import annotations

import json
from pathlib import Path

from .longboard_plan import LongboardError
from .unified_classroom_flow import canonical_sha

REQUIRED = frozenset({
    "version", "problem_type", "opening", "strategy", "knowledge",
    "pitfalls", "conclusion", "recap",
})
CATEGORIES = frozenset({"formula", "theorem", "definition", "property", "method", "principle"})


def _error(message: str) -> None:
    raise LongboardError("V27_" + message)


def _check_record(value, keys, code):
    if not isinstance(value, dict) or set(value) != set(keys):
        _error(code)


def _excerpt(text: str, phrase: str, code: str) -> None:
    if not isinstance(phrase, str) or len(phrase.strip()) < 3 or phrase not in text:
        _error(code)


def _in_order(text: str, phrases: list[str], code: str) -> None:
    cursor = 0
    for phrase in phrases:
        if not isinstance(phrase, str) or not phrase.strip():
            _error(code)
        index = text.find(phrase, cursor)
        if index < 0:
            _error(code)
        cursor = index + len(phrase)


def _actual_events(flow, events):
    rows = []
    by_id = {}
    for stage in flow.stages:
        cues = stage.cues["events"]
        stage_events = [e for e in events if e.stage_id == stage.stage_id]
        if len(cues) != len(stage_events):
            _error("CUE_EVENT_MISMATCH")
        for cue, event in zip(cues, stage_events):
            if cue["event_id"] != event.event_id or event.event_id in by_id:
                _error("CUE_EVENT_ID_NOT_UNIQUE")
            entry = {
                "id": event.event_id,
                "phase": cue["phase"],
                "heading": cue["heading"],
                "detail": cue["detail"],
                "event": event,
                "stage": stage.stage_id,
            }
            rows.append(entry)
            by_id[event.event_id] = entry
    if len(rows) != len(events):
        _error("EVENTS_UNACCOUNTED")
    return rows, by_id


def _voice(entry):
    return "".join(span.tts_text for span in entry["event"].spans)


def check_v27_teacher_contract(flow, events, contract: dict) -> dict:
    """Fail closed for V2.7 lesson order, exact question source, and voiced claims."""
    if not isinstance(contract, dict) or set(contract) != REQUIRED or contract.get("version") != "2.7":
        _error("CONTRACT_FIELDS")
    if not isinstance(contract["problem_type"], str) or not contract["problem_type"].strip():
        _error("PROBLEM_TYPE")
    rows, by_id = _actual_events(flow, events)
    order = {entry["id"]: i for i, entry in enumerate(rows)}

    def event(record, phase, code):
        if not isinstance(record, dict) or not isinstance(record.get("event_id"), str):
            _error(code)
        item = by_id.get(record["event_id"])
        if item is None or item["phase"] != phase:
            _error(code)
        return item

    opening = contract["opening"]
    _check_record(opening, {"event_id", "opening_text", "question_segments"}, "OPENING_FIELDS")
    first = event(opening, "observe", "OPENING_NOT_FIRST_OBSERVE")
    if first is not rows[0]:
        _error("OPENING_ORDER")
    greeting = "同学们大家好，我们先来看一下这道" + contract["problem_type"] + "题。"
    if opening["opening_text"] != greeting or not _voice(first).startswith(greeting):
        _error("OPENING_GREETING_NOT_SPOKEN")
    question = opening["question_segments"]
    if not isinstance(question, list) or not question:
        _error("QUESTION_SEGMENTS")
    originals, readings = [], []
    full_math_readings = [
        part["reading"] for span in first["event"].spans
        for part in span.parts if part["kind"] == "math"
    ]
    for part in question:
        _check_record(part, {"source_text", "spoken_text"}, "QUESTION_PART_FIELDS")
        originals.append(part["source_text"])
        readings.append(part["spoken_text"])
        # A LaTeX-bearing source segment must cite the COMPLETE approved
        # mathematical pronunciation, not a tiny token such as "I 等于".
        if not any(ord(ch) == 92 for ch in part["source_text"]):
            if part["spoken_text"].strip() != part["source_text"].strip():
                _error("QUESTION_ORIGINAL_WORDS_PARAPHRASED")
        elif part["spoken_text"] not in full_math_readings:
            _error("QUESTION_MATH_READING_NOT_COMPLETE")
    if "".join(originals) != flow.problem:
        _error("QUESTION_NOT_FULL_SOURCE")
    _in_order(_voice(first), readings, "QUESTION_NOT_FULLY_AUDIBLE")

    strategy = contract["strategy"]
    _check_record(strategy, {"event_id", "why_method"}, "STRATEGY_FIELDS")
    idea = event(strategy, "strategy", "STRATEGY_EVENT_MISSING")
    _excerpt(_voice(idea), strategy["why_method"], "STRATEGY_NOT_SPOKEN")
    if not order[first["id"]] < order[idea["id"]]:
        _error("STRATEGY_AFTER_QUESTION")

    knowledge = contract["knowledge"]
    if not isinstance(knowledge, list) or not knowledge:
        _error("KNOWLEDGE_REQUIRED")
    source_knowledge = {x["id"] for x in rows if x["phase"] == "knowledge"}
    seen_knowledge = set()
    for item in knowledge:
        _check_record(item, {"event_id", "kind", "title", "math_latex",
                             "spoken_explanation", "applied_event_id"}, "KNOWLEDGE_FIELDS")
        source = event(item, "knowledge", "KNOWLEDGE_PHASE")
        if item["event_id"] in seen_knowledge or item["kind"] not in CATEGORIES:
            _error("KNOWLEDGE_DUPLICATE_OR_KIND")
        seen_knowledge.add(item["event_id"])
        if item["title"] != source["heading"]:
            _error("KNOWLEDGE_TITLE_MISMATCH")
        _excerpt(_voice(source), item["spoken_explanation"], "KNOWLEDGE_NOT_SPOKEN")
        formal = item["math_latex"]
        if item["kind"] == "method":
            if formal is not None and (not isinstance(formal, str) or
                not any(s.math_latex == formal for s in source["event"].spans)):
                _error("METHOD_FORMULA_NOT_ON_BOARD")
        else:
            if (not isinstance(formal, str) or
                    not any(s.math_latex == formal for s in source["event"].spans)):
                _error("KNOWLEDGE_FORMULA_NOT_ON_BOARD")
        application = by_id.get(item["applied_event_id"])
        if application is None or order[application["id"]] <= order[source["id"]]:
            _error("KNOWLEDGE_WITHOUT_FOLLOWING_APPLICATION")
    if seen_knowledge != source_knowledge:
        _error("KNOWLEDGE_BOARD_COVERAGE")

    pitfalls = contract["pitfalls"]
    if not isinstance(pitfalls, list):
        _error("PITFALL_FIELDS")
    pitfall_ids = {x["id"] for x in rows if x["phase"] == "pitfall"}
    seen_pitfalls = set()
    for item in pitfalls:
        _check_record(item, {"event_id", "typical_mistake", "correction",
                             "spoken_mistake", "spoken_correction"}, "PITFALL_FIELDS")
        cue = event(item, "pitfall", "PITFALL_PHASE")
        if item["event_id"] in seen_pitfalls:
            _error("PITFALL_DUPLICATE")
        seen_pitfalls.add(item["event_id"])
        if not item["typical_mistake"].strip() or not item["correction"].strip():
            _error("PITFALL_EMPTY")
        _in_order(_voice(cue), [
            item["spoken_mistake"], item["spoken_correction"]
        ], "PITFALL_NOT_AUDIBLE")
    if seen_pitfalls != pitfall_ids:
        _error("PITFALL_BOARD_COVERAGE")

    conclusion = contract["conclusion"]
    recap = contract["recap"]
    _check_record(conclusion, {"event_id", "spoken_result"}, "CONCLUSION_FIELDS")
    _check_record(recap, {"event_id", "spoken_recap"}, "RECAP_FIELDS")
    answer = event(conclusion, "conclusion", "CONCLUSION_PHASE")
    summary = event(recap, "summary", "RECAP_PHASE")
    if order[summary["id"]] != len(rows)-1 or not (
        order[idea["id"]] < order[answer["id"]] < order[summary["id"]]
    ):
        _error("RECAP_MUST_FOLLOW_CONCLUSION")
    if any(order[answer["id"]] <= order[k] for k in seen_knowledge | seen_pitfalls):
        _error("KNOWLEDGE_OR_PITFALL_AFTER_ANSWER")
    if not any(s.kind == "math" for s in answer["event"].spans):
        _error("CONCLUSION_WITHOUT_BOARD")
    _excerpt(_voice(answer), conclusion["spoken_result"], "CONCLUSION_NOT_SPOKEN")
    _excerpt(_voice(summary), recap["spoken_recap"], "RECAP_NOT_SPOKEN")

    return {
        "contract_version": "2.7",
        "question_source_coverage": "exact_full_original_text",
        "opening_tts_segments_covered": len(question),
        "knowledge_covered": len(knowledge),
        "pitfalls_covered": len(pitfalls),
        "recap_after_result": True,
        "note": "Audible excerpts and source order validated; semantic truth still needs human review",
    }


def compile_spoken_script(contract, *, source_document: dict | None = None) -> tuple[dict, str]:
    """Pre-render machine-verified script with all actual planned visual writes."""
    rows, by_id = _actual_events(contract.flow, contract.events)
    spec = None if source_document is None else source_document.get("lesson_contract")
    evidence = check_v27_teacher_contract(contract.flow, contract.events, spec) if spec else {
        "contract_version": "legacy",
        "note": "Legacy event coverage only; not V2.7 classroom certified",
    }
    entries = []
    for row in rows:
        actions = []
        for span in row["event"].spans:
            item = {
                "kind": span.kind,
                "object_id": span.object_id,
                "spoken_parts": list(span.parts),
                "spoken_exact": span.tts_text,
            }
            if span.kind == "math":
                item["board_math_latex"] = span.math_latex
            elif span.kind == "note":
                item["board_heading"] = row["heading"]
                item["board_detail"] = row["detail"]
            elif span.kind == "diagram":
                item["diagram_source_id"] = span.object_id
            actions.append(item)
        entries.append({
            "stage_id": row["stage"], "event_id": row["id"],
            "phase": row["phase"], "heading": row["heading"],
            "source_board_detail": row["detail"],
            "actions": actions,
        })
    document = {
        "schema_version": "2.7", "source_spoken_sha256": contract.source_sha256,
        "lesson_id": contract.flow.lesson_id, "full_original_question": contract.flow.problem,
        "acceptance": evidence, "events": entries,
    }
    lines = [
        "# 真实教师完整口播与板书脚本（渲染前审核）", "",
        "题干原文（逐段全文核对）：" + contract.flow.problem, "",
    ]
    for row in entries:
        lines.extend([
            "## " + row["event_id"] + " · " + row["phase"] + " · " + row["heading"],
            "",
        ])
        for i, action in enumerate(row["actions"], 1):
            lines.append(str(i) + ". [" + action["kind"] + "] " + action["object_id"])
            if "board_math_latex" in action:
                lines.append("   - 板书 MathTex：" + action["board_math_latex"])
            if "board_heading" in action:
                lines.append("   - 板书讲解：" + action["board_heading"] + "；" + action["board_detail"])
            if "diagram_source_id" in action:
                lines.append("   - 图形对象：" + action["diagram_source_id"])
            lines.append("   - 完整口播：" + action["spoken_exact"])
        lines.append("")
    lines.append("验收说明：此稿保留逐动作完整原话，TTS 发音时间与成片同步仍需在真实渲染后核对。")
    return document, "\n".join(lines) + "\n"


def export_spoken_script(approved, *, output_json: Path, output_md: Path,
                         source_document: dict | None = None) -> dict:
    doc, readable = compile_spoken_script(approved, source_document=source_document)
    for dest in (output_json, output_md):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(output_json).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Path(output_md).write_text(readable, encoding="utf-8")
    return doc


def require_prerender_script(contract, path: Path) -> dict:
    """For new V2.7 lessons the script must have been exported BEFORE TTS."""
    script = path.parent / "lesson_script.json"
    if not script.is_file():
        _error("SCRIPT_MUST_BE_EXPORTED_BEFORE_RENDER")
    try:
        document = json.loads(script.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise LongboardError("V27_SCRIPT_INVALID_JSON") from exc
    if document.get("source_spoken_sha256") != contract.source_sha256:
        _error("SCRIPT_CHANGED_AFTER_APPROVAL")
    if document.get("acceptance", {}).get("contract_version") != "2.7":
        _error("SCRIPT_NOT_V27_ACCEPTED")
    from .unified_classroom_flow import _load
    authoritative, _ = compile_spoken_script(
        contract, source_document=_load(path)
    )
    if document != authoritative:
        _error("SCRIPT_CONTENT_TAMPERED_OR_INCOMPLETE")
    return document
