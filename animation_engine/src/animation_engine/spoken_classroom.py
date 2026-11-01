"""V2.6.4 teacher-reviewed complete classroom narration contract.

Every genuinely displayed note, newly revealed diagram and MathTex write
gets its own audibly spoken semantic segment. Written mathematics and
caption mathematics are identical reviewed LaTeX; voice pronunciation is
an independent, teacher-authored Chinese reading, never displayed.

This validator checks provenance and *declared* pedagogical coverage.
It cannot prove that Chinese prose is pedagogically complete; the human
teacher/content reviewer remains accountable for the actual words.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .longboard_plan import LongboardError, _sources
from .unified_classroom_flow import Flow, canonical_sha, checked_flow, _load

ROOT = frozenset({
    "schema_version", "mode", "teacher_reviewed", "source_flow_sha256",
    "voice", "events",
})
OPTIONAL_ROOT = frozenset({"speech_rate", "lesson_contract"})
# Previously approved Yunxi speech used -4%. +1% is approximately 5.2%
# faster in the Edge TTS speed setting; exact acoustic duration is measured.
DEFAULT_SPEECH_RATE = "+1%"
EVENT = frozenset({
    "stage_id", "event_id", "pedagogical_cue_covered", "spans",
    "question_read_aloud", "question_source_sha256",
})
SPAN = frozenset({"kind", "object_id", "parts"})
EVENT_WITH_FACTS = EVENT | {"question_fact_alignment"}
SPAN_WITH_DIAGRAM_CUES = SPAN | {"diagram_phrase_cues"}
TEXT_PART = frozenset({"kind", "value"})
MATH_PART = frozenset({"kind", "latex", "reading"})
MATH_PART_WITH_CAPTION = MATH_PART | {"spoken_math_latex"}
KINDS = frozenset({"diagram", "note", "math"})
# These are references to an external solution, never legitimate reasons for
# a mathematical classroom derivation. Saying the answer *is* a number is fine.
FORBIDDEN = re.compile(
    r"(?:按照|根据|依据|参考|照着|依照|看(?:一下)?)\s*"
    r"(?:这份|那个|标准|参考|原)?\s*(?:答案|解答|题解)"
    r"|(?:由|从|按|依照|依据)\s*(?:标准|参考|原)?\s*答案"
    r"|(?:参考答案|标准答案|原答案|答案里|答案中|"
    r"题解里|题解中|解答里|解答中|讲义答案|参考解法)"
)
# Classroom narration must describe mathematical ideas, not the renderer,
# screen/pagination mechanics or formula-introduction placeholders.
# These intentionally narrow phrases are independent of voice and topic.
CLASSROOM_META = re.compile(
    r"(?:上一|下一)(?:页|屏|幕)"
    r"|(?:上|下)一(?:个)?(?:画面|场景|镜头)"
    r"|(?:计算|展示|演示|公式|板书|答题)区(?!间)"
    r"|(?:把|将)[^。！？]{0,20}(?:搬到|移到|接到)(?:计算|展示|板书|公式)区"
)
STILTED_TRANSITION = re.compile(
    r"其公式为|对应的公式(?:为|是)|现在(?:展示|呈现)(?:计算|最终)?(?:公式|结果)"
)

VOICES = frozenset({
    "zh-CN-YunxiNeural", "zh-CN-YunjianNeural",
    "zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural",
})


@dataclass(frozen=True)
class SpokenSpan:
    kind: str
    object_id: str
    parts: tuple[dict, ...]
    tts_text: str
    math_latex: str | None
    diagram_phrase_cues: tuple[dict, ...] = ()


@dataclass(frozen=True)
class SpokenEvent:
    stage_id: str
    event_id: str
    spans: tuple[SpokenSpan, ...]


@dataclass(frozen=True)
class SpokenContract:
    flow: Flow
    source_sha256: str
    voice: str
    events: tuple[SpokenEvent, ...]
    speech_rate: str = DEFAULT_SPEECH_RATE

    def grouped(self) -> dict[str, dict[str, SpokenEvent]]:
        result: dict[str, dict[str, SpokenEvent]] = {}
        for e in self.events:
            result.setdefault(e.stage_id, {})[e.event_id] = e
        return result


def _expected_actions(flow: Flow, *, measure=None, adaptive=False) -> list[dict]:
    from .persistent_chalkboard import make_chalkboard_plan
    from .models import ExecutionPlan
    from .adaptive_layout import GlyphSize
    result = []
    for stage in flow.stages:
        opts = {}
        if adaptive:
            # Layout is source-authored in the separate V2.6.2 flow; validate
            # that contract first. This planner only needs action/order.
            from .adaptive_classroom_flow import checked_adaptive_flow
            spec = next(x for x in checked_adaptive_flow(
                stage.folder.parent / "adaptive_layout.json").stages
                if x.stage_id == stage.stage_id)
            opts["layout_hint"] = (
                "diagram_left" if spec.layout == "math_left_diagram_right"
                else "preserve_diagram" if spec.layout == "diagram_native"
                else None
            )
        def _cheap_size(latex, scale):
            return GlyphSize(170, 40)
        board = make_chalkboard_plan(
            stage.storyboard, stage.execution, stage.cues, stage.policy,
            measure=measure or _cheap_size, **stage.kwargs(), **opts,
        )
        maths = _sources(ExecutionPlan.model_validate(stage.execution))
        for event in board["events"]:
            expected = []
            diagram = (
                ("diagram", "diagram:" + event["event_id"], None)
                if event.get("diagram_reveal_ids") else None
            )
            if diagram and event["diagram_order"] == "diagram_then_math":
                expected.append(diagram)
            for block in event["added_blocks"]:
                ident = block["block_id"]
                expected.append((
                    "note" if block["kind"] == "teacher_note" else "math",
                    ident, maths[ident]["latex"] if block["kind"] == "math"
                    else None
                ))
            if diagram and event["diagram_order"] == "math_then_diagram":
                expected.append(diagram)
            result.append({
                "stage_id": stage.stage_id, "event_id": event["event_id"],
                "actions": expected,
                "diagram_reveal_ids": list(event.get("diagram_reveal_ids", [])),
            })
    return result


def checked_spoken(input_file: Path | str, *, adaptive=False,
                   measure=None) -> SpokenContract:
    path = Path(input_file).resolve()
    doc = _load(path)
    if (not ROOT.issubset(doc) or not set(doc).issubset(ROOT | OPTIONAL_ROOT) or doc["schema_version"] != "1.0"
            or doc["mode"] != "verified_spoken_classroom"
            or doc["teacher_reviewed"] is not True):
        raise LongboardError("SPOKEN_INVALID_MANIFEST")
    flow = checked_flow(path.parent / "unified_flow.json")
    if doc["source_flow_sha256"] != flow.source_sha256:
        raise LongboardError("SPOKEN_SOURCE_CHANGED")
    if doc["voice"] not in VOICES:
        raise LongboardError("SPOKEN_VOICE_NOT_APPROVED")
    rate = doc.get("speech_rate", DEFAULT_SPEECH_RATE)
    if type(rate) is not str or not re.fullmatch(r"[+-](?:[0-9]|[12][0-9]|30)%", rate):
        raise LongboardError("SPOKEN_RATE_NOT_APPROVED")
    # A positive source-bound statement of which screen objects were
    # actually drawn is stronger than counting formulas in a script.
    required = _expected_actions(flow, measure=measure, adaptive=adaptive)
    if (not isinstance(doc["events"], list)
            or len(doc["events"]) != len(required)):
        raise LongboardError("SPOKEN_EVENT_COVERAGE")
    validated = []
    for index,(recorded, planned) in enumerate(zip(doc["events"], required)):
        if not isinstance(recorded, dict) or set(recorded) not in (EVENT, EVENT_WITH_FACTS):
            raise LongboardError("SPOKEN_EVENT_FIELDS")
        if (recorded["stage_id"], recorded["event_id"]) != (
                planned["stage_id"], planned["event_id"]):
            raise LongboardError("SPOKEN_EVENT_ORDER")
        if recorded["pedagogical_cue_covered"] is not True:
            raise LongboardError("SPOKEN_TEACHING_CUE_UNCOVERED")
        if index == 0:
            if recorded["question_read_aloud"] is not True:
                raise LongboardError("SPOKEN_QUESTION_NOT_READ")
            if recorded["question_source_sha256"] != canonical_sha(flow.problem):
                raise LongboardError("SPOKEN_QUESTION_SOURCE_MUTATED")
        elif (recorded["question_read_aloud"] is not False or
              recorded["question_source_sha256"] is not None):
            raise LongboardError("SPOKEN_QUESTION_DUPLICATED_ON_NEW_STAGE")
        spans = recorded["spans"]
        if not isinstance(spans, list) or len(spans) != len(planned["actions"]):
            raise LongboardError("SPOKEN_ACTION_COVERAGE")
        checked = []
        for row, (kind, ident, latex) in zip(spans, planned["actions"]):
            if not isinstance(row, dict) or set(row) not in (SPAN, SPAN_WITH_DIAGRAM_CUES):
                raise LongboardError("SPOKEN_SPAN_FIELDS")
            diagram_cues = row.get("diagram_phrase_cues", [])
            if (row["kind"], row["object_id"]) != (kind, ident):
                raise LongboardError("SPOKEN_ACTION_ORDER")
            if not isinstance(row["parts"], list) or not row["parts"]:
                raise LongboardError("SPOKEN_SILENT_ACTION")
            voice = []
            text_count = 0
            maths = []
            parts = []
            for p in row["parts"]:
                if not isinstance(p, dict):
                    raise LongboardError("SPOKEN_BAD_PART")
                if p.get("kind") == "text" and set(p) == TEXT_PART:
                    val = p["value"]
                    if (type(val) is not str or not val.strip()
                            or "\\" in val or "$" in val or len(val) > 170):
                        raise LongboardError("SPOKEN_TEXT_NOT_NATURAL")
                    text_count += 1
                    voice.append(val)
                    parts.append(dict(p))
                elif p.get("kind") == "math" and set(p) in (MATH_PART, MATH_PART_WITH_CAPTION):
                    from .mathtex_renderer import validate_math_latex
                    validate_math_latex(p["latex"])
                    if "spoken_math_latex" in p:
                        caption_math = p["spoken_math_latex"]
                        if (not isinstance(caption_math, str) or
                                caption_math == p["latex"] or
                                caption_math not in p["latex"]):
                            raise LongboardError("SPOKEN_CAPTION_MATH_NOT_A_REVIEWED_SOURCE_FRAGMENT")
                        validate_math_latex(caption_math)
                    reading = p["reading"]
                    if (type(reading) is not str or not reading.strip()
                            or "\\" in reading or "$" in reading
                            or len(reading) > 200):
                        raise LongboardError("SPOKEN_MATH_PRONUNCIATION_MISSING")
                    maths.append(p["latex"])
                    voice.append(reading)
                    parts.append(dict(p))
                else:
                    raise LongboardError("SPOKEN_BAD_PART")
            if kind == "math" and latex not in maths:
                raise LongboardError("SPOKEN_MATH_NOT_READ")
            if kind != "math" and maths:
                # Visual-only note and diagram utterances should not smuggle
                # uncited/novel formulas onto the screen through subtitles.
                raise LongboardError("SPOKEN_UNSOURCED_CAPTION_MATH")
            if text_count == 0:
                raise LongboardError("SPOKEN_NO_TEACHING_EXPLANATION")
            actual = "".join(voice)
            if FORBIDDEN.search(actual):
                raise LongboardError("SPOKEN_EXTERNAL_ANSWER_REFERENCE")
            if CLASSROOM_META.search(actual):
                raise LongboardError("SPOKEN_CLASSROOM_META_LANGUAGE")
            if STILTED_TRANSITION.search(actual):
                raise LongboardError("SPOKEN_STILTED_TRANSITION")
            if diagram_cues:
                from .spoken_audio import split_natural_phrases
                if kind != "diagram" or not isinstance(diagram_cues, list):
                    raise LongboardError("SPOKEN_DIAGRAM_BEATS_INVALID")
                candidates = [
                    phrase for part in parts if part["kind"] == "text"
                    for phrase in split_natural_phrases(part["value"])
                ]
                requested = []
                positions = []
                missing_phrase = False
                for cue in diagram_cues:
                    if (not isinstance(cue, dict) or
                            set(cue) != {"object_id", "phrase"} or
                            cue["object_id"] not in planned["diagram_reveal_ids"] or
                            type(cue["phrase"]) is not str):
                        raise LongboardError("SPOKEN_DIAGRAM_BEATS_UNSOURCED")
                    if cue["phrase"] not in candidates:
                        missing_phrase = True
                    else:
                        positions.append(candidates.index(cue["phrase"]))
                    requested.append(cue["object_id"])
                ids = planned["diagram_reveal_ids"]
                if (len(set(requested)) != len(requested) or
                        requested != sorted(requested, key=ids.index)):
                    raise LongboardError("SPOKEN_DIAGRAM_BEATS_ORDER")
                if missing_phrase:
                    # A free-language edit can replace the whole explanation.
                    # If it makes no promise to draw or label anything, fall
                    # back to event timing instead of rejecting unrelated text.
                    # Any actual drawing command MUST keep reviewed anchors.
                    if re.search(r"画出|绘制|连接|连线|标出|标上|画直角|画线", actual):
                        raise LongboardError("SPOKEN_DIAGRAM_BEATS_UNSOURCED")
                    diagram_cues = []
                elif positions != sorted(positions):
                    raise LongboardError("SPOKEN_DIAGRAM_BEATS_ORDER")
            elif "diagram_phrase_cues" in row and kind != "diagram":
                raise LongboardError("SPOKEN_DIAGRAM_BEATS_INVALID")
            checked.append(SpokenSpan(kind, ident, tuple(parts), actual, latex,
                                     tuple(dict(c) for c in diagram_cues)))
        if "question_fact_alignment" in recorded:
            facts = recorded["question_fact_alignment"]
            if index != 0 or not isinstance(facts, list) or not facts:
                raise LongboardError("SPOKEN_QUESTION_FACTS_NOT_OPENING")
            voice_actual = " ".join(span.tts_text for span in checked)
            visited = set()
            for fact in facts:
                if (not isinstance(fact, dict) or
                        set(fact) != {"source_excerpt", "spoken_excerpt"} or
                        not isinstance(fact["source_excerpt"], str) or
                        not isinstance(fact["spoken_excerpt"], str) or
                        not fact["source_excerpt"] or
                        not fact["spoken_excerpt"] or
                        fact["source_excerpt"] not in flow.problem or
                        fact["spoken_excerpt"] not in voice_actual or
                        fact["source_excerpt"] in visited):
                    raise LongboardError("SPOKEN_QUESTION_FACT_NOT_AUDIBLE_OR_SOURCED")
                visited.add(fact["source_excerpt"])
        validated.append(SpokenEvent(
            recorded["stage_id"], recorded["event_id"], tuple(checked)
        ))
    if "lesson_contract" in doc:
        from .v27_teacher_contract import check_v27_teacher_contract
        check_v27_teacher_contract(flow, tuple(validated), doc["lesson_contract"])
    return SpokenContract(flow, canonical_sha(doc), doc["voice"], tuple(validated), rate)


def plan_spoken(input_file: Path | str, *, adaptive=False, measure=None) -> dict:
    checked = checked_spoken(input_file, adaptive=adaptive, measure=measure)
    return {
        "schema_version": "1.0", "mode": "verified_spoken_classroom",
        "source_spoken_sha256": checked.source_sha256,
        "source_flow_sha256": checked.flow.source_sha256,
        "voice": checked.voice,
        "speech_rate": checked.speech_rate,
        "event_count": len(checked.events),
        "action_count": sum(len(x.spans) for x in checked.events),
        "pedagogical_cue_coverage": "teacher_reviewed_all",
        "math_writes_all_voiced": True,
        "formula_caption_policy": "source_mathtex_not_phonetic_transliteration",
        "forbidden_answer_source_phrases_rejected": True,
        "voice_status": "not_generated",
        "subtitle_status": "not_aligned",
        "events": [{
            "global_event_id": x.stage_id + ":" + x.event_id,
            "actions": [{
                "kind": s.kind, "object_id": s.object_id,
                "tts_text": s.tts_text, "parts": list(s.parts),
            } for s in x.spans],
        } for x in checked.events],
    }
