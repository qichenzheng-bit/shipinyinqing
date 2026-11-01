"""V2.7 regression guards: genuine source coverage, voiced knowledge and recap."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from animation_engine.longboard_plan import LongboardError
from animation_engine.v27_teacher_contract import (
    check_v27_teacher_contract, compile_spoken_script, require_prerender_script,
)


def lesson():
    problem = "计算定积分：x"
    rows = [
        ("e_intro", "observe", "完整读题", "同学们大家好，我们先来看一下这道定积分题。题目要求计算定积分。x"),
        ("e_strategy", "strategy", "分析结构", "为什么考虑换元法？因为出现内层导数。"),
        ("e_knowledge", "knowledge", "定积分换元法", "这里使用定积分换元法，并替换积分上下限。"),
        ("e_apply", "calculate", "换元", "令 u 等于 x 的平方。"),
        ("e_pitfall", "pitfall", "易错点", "错误是保留原来的积分上限。正确做法是重算新上限。"),
        ("e_conclusion", "conclusion", "最后答案", "最终的结果是 e 的四次方减一。"),
        ("e_summary", "summary", "归纳总结", "最后归纳一下，先认出内层导数，再检查新积分限。"),
    ]
    cue_rows = [{"event_id": eid, "phase": phase, "heading": title, "detail": title}
                for eid, phase, title, _ in rows]
    stage = SimpleNamespace(stage_id="integration", cues={"events":cue_rows})
    events = []
    for eid, phase, title, voice in rows:
        spans = [
            SimpleNamespace(kind="note", object_id="n_"+eid, tts_text=voice,
                            parts=({"kind":"text","value":voice},), math_latex=None)
        ]
        if eid in ("e_knowledge", "e_conclusion"):
            tex = "u=g(x)" if eid == "e_knowledge" else "I=e^4-1"
            spans.append(SimpleNamespace(kind="math", object_id="m_"+eid,
                                        tts_text="读这个数学公式。",
                                        parts=({"kind":"math","latex":tex,"reading":"读这个数学公式。"},),
                                        math_latex=tex))
        events.append(SimpleNamespace(stage_id="integration", event_id=eid,
                                     spans=tuple(spans)))
    flow = SimpleNamespace(stages=(stage,), problem=problem, lesson_id="sample")
    spec = {
        "version": "2.7", "problem_type": "定积分",
        "opening": {
            "event_id": "e_intro", "opening_text": "同学们大家好，我们先来看一下这道定积分题。",
            "question_segments": [
                {"source_text": "计算定积分：", "spoken_text": "题目要求计算定积分"},
                {"source_text": "x", "spoken_text": "x"},
            ],
        },
        "strategy": {"event_id": "e_strategy", "why_method":"为什么考虑换元法？因为出现内层导数。"},
        "knowledge": [{"event_id":"e_knowledge", "kind":"formula", "title":"定积分换元法",
                      "math_latex":"u=g(x)", "spoken_explanation":"这里使用定积分换元法",
                      "applied_event_id":"e_apply"}],
        "pitfalls": [{"event_id":"e_pitfall", "typical_mistake":"保留旧积分限",
                     "correction":"计算新积分限",
                     "spoken_mistake":"错误是保留原来的积分上限。",
                     "spoken_correction":"正确做法是重算新上限。"}],
        "conclusion": {"event_id":"e_conclusion", "spoken_result":"最终的结果是 e 的四次方减一。"},
        "recap": {"event_id":"e_summary", "spoken_recap":"最后归纳一下，先认出内层导数"},
    }
    return flow, events, spec


def test_complete_original_question_and_knowledge_and_recap():
    flow, events, spec = lesson()
    out = check_v27_teacher_contract(flow, events, spec)
    assert out["contract_version"] == "2.7"
    assert out["recap_after_result"]
    assert out["knowledge_covered"] == 1
    assert out["opening_tts_segments_covered"] == 2


def test_missing_question_character_fails_closed():
    flow, events, spec = lesson()
    spec["opening"]["question_segments"][0]["source_text"] = "计算积分："
    with pytest.raises(LongboardError, match="V27_QUESTION_NOT_FULL_SOURCE"):
        check_v27_teacher_contract(flow, events, spec)


def test_omitted_knowledge_speech_fails_closed():
    flow, events, spec = lesson()
    spec["knowledge"][0]["spoken_explanation"] = "没有说过这句话"
    with pytest.raises(LongboardError, match="V27_KNOWLEDGE_NOT_SPOKEN"):
        check_v27_teacher_contract(flow, events, spec)


def test_recap_cannot_be_final_result_event():
    flow, events, spec = lesson()
    spec["recap"]["event_id"] = "e_conclusion"
    with pytest.raises(LongboardError, match="V27_RECAP_PHASE"):
        check_v27_teacher_contract(flow, events, spec)


def test_pitfall_correction_must_be_audible():
    flow, events, spec = lesson()
    spec["pitfalls"][0]["spoken_correction"] = "下限要减去两"
    with pytest.raises(LongboardError, match="V27_PITFALL_NOT_AUDIBLE"):
        check_v27_teacher_contract(flow, events, spec)


def test_prerender_script_blocks_missing_and_changed_source(tmp_path):
    contract = SimpleNamespace(source_sha256="approved")
    spoken = tmp_path / "spoken_classroom.json"
    with pytest.raises(LongboardError, match="V27_SCRIPT_MUST_BE_EXPORTED"):
        require_prerender_script(contract, spoken)
    (tmp_path / "lesson_script.json").write_text(
        '{"source_spoken_sha256":"changed","acceptance":{"contract_version":"2.7"}}'
    )
    with pytest.raises(LongboardError, match="V27_SCRIPT_CHANGED_AFTER_APPROVAL"):
        require_prerender_script(contract, spoken)


def test_complete_script_lists_math_and_spoken_source():
    flow, events, spec = lesson()
    approved = SimpleNamespace(flow=flow, events=tuple(events), source_sha256="approved")
    result, markdown = compile_spoken_script(approved, source_document={"lesson_contract":spec})
    assert result["full_original_question"] == flow.problem
    assert "u=g(x)" in markdown
    assert "最后归纳一下" in markdown
    assert all(e["actions"] for e in result["events"])


def test_method_only_knowledge_uses_explicit_reusable_procedure_not_fake_formula():
    from animation_engine.core_knowledge import checked_core_knowledge
    units = [
        {"id": "method", "phase": "knowledge", "heading": "分组讨论法",
         "math": [{"id": "example", "latex": "x>0", "reason": "例题分情况"}]},
        {"id": "application", "phase": "calculate", "heading": "处理区间",
         "math": [{"id": "case", "latex": "x<0", "reason": "例题分情况"}]},
    ]
    point = {
        "event_id": "e_method", "topic_id": "case_split", "title": "分组讨论法",
        "kind": "method", "formulae": [],
        "method_description": "依据变量取值范围分情况证明，逐一穷尽可能性",
        "used_in": ["e_application"],
    }
    catalog = {"schema_version": "1.0", "teacher_reviewed": True, "points": [point]}
    assert checked_core_knowledge(units, catalog) == catalog
    point["method_description"] = "代入"
    with pytest.raises(LongboardError, match="CORE_KNOWLEDGE_METHOD_REQUIRED"):
        checked_core_knowledge(units, catalog)
