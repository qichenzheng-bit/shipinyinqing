"""The seven real-video audit regressions, without video/media dependencies."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))

from build_independent_log_limit_final_qa import build
from animation_engine.classroom_cues import BOARD_TEXT_STYLE, BOARD_DETAIL_FONT_PX
from animation_engine.longboard_plan import LongboardError
from animation_engine.persistent_chalkboard import make_chalkboard_plan
from animation_engine.spoken_audio import (
    VoiceChunk, VoicedSpan, build_render_schedules, split_natural_phrases,
)
from animation_engine.spoken_classroom import checked_spoken, _expected_actions
from animation_engine.unified_classroom_flow import checked_flow
from animation_engine.v27_teacher_contract import compile_spoken_script
from animation_engine.video_settings import DEFAULT_VIDEO_FPS


@pytest.fixture
def sample(tmp_path):
    folder=tmp_path/"new-logarithmic-limit"
    builder=build(folder)
    flow=checked_flow(folder/"unified_flow.json")
    contract=checked_spoken(folder/"spoken_classroom.json",adaptive=False)
    plan=make_chalkboard_plan(
        flow.stages[0].storyboard,
        flow.stages[0].execution,
        flow.stages[0].cues,
        flow.stages[0].policy,
        measure=lambda latex,scale: __import__(
            "animation_engine.adaptive_layout",fromlist=["GlyphSize"]
        ).GlyphSize(170,40),
    )
    return folder,builder,contract,plan


def test_question_is_sourced_and_speech_only_in_fixed_header(sample):
    folder,doc,contract,plan=sample
    first=plan["events"][0]
    assert first["event_id"]=="e_intro"
    assert first["math_write_count"]==0
    assert first["added_blocks"]==[]
    assert [a["kind"] for a in first["speech_only_actions"]]==["note","math"]
    assert first["visible_block_ids"]==[]
    expected=_expected_actions(contract.flow)
    assert [a[0] for a in expected[0]["actions"]]==["note","math"]
    actual=doc["events"][0]["spans"]
    assert actual[1]["parts"][0]["value"]=="求极限："
    info,markdown=compile_spoken_script(
        contract,source_document=doc
    )
    math=next(a for a in info["events"][0]["actions"] if a["kind"]=="math")
    assert "header_math_latex" in math and "board_math_latex" not in math
    assert "仅朗读" in markdown


def test_conclusion_stays_in_solution_and_summary_only_reviews_knowledge(sample):
    folder,doc,contract,plan=sample
    rows={e["event_id"]:e for e in plan["events"]}
    conclusion=rows["e_conclusion"]
    summary=rows["e_summary"]
    assert "m_conclusion" in conclusion["visible_block_ids"]
    assert summary["page_index"]>conclusion["page_index"]
    assert summary["erase_before"]
    # Explicitly requested: no final-answer block on the recap page.
    assert "m_conclusion" not in summary["visible_block_ids"]
    assert "m_conclusion" not in summary["carry_object_ids"]
    # Previously verified MathTex is displayed again without a new write,
    # pronunciation, calculation or fabricated educational source.
    assert "m_knowledge" in summary["visible_block_ids"]
    assert "m_knowledge" in summary["carry_object_ids"]
    assert summary["math_write_count"]==0
    assert any(b["block_id"]=="m_knowledge" and b.get("recap_review")
               and b.get("carry") for b in summary["added_blocks"])
    assert any(b["kind"]=="teacher_note" and b.get("recap_review")
               and b["phase"]=="pitfall" and "易错点" in b["heading"]
               for b in summary["added_blocks"])
    assert "m_knowledge" in summary["recap_review_source_ids"]
    assert not any(b.get("recap_review") and b["block_id"]=="m_conclusion"
                   for b in summary["added_blocks"])


def test_verified_cancellation_has_real_source_phrase_and_highlight(sample):
    folder,doc,contract,plan=sample
    spans=next(e for e in doc["events"] if e["event_id"]=="e_cancel")["spans"]
    actions=[s for s in spans if s["kind"]=="math"]
    assert len(actions)==1 and len(actions[0]["emphasis_cues"])>=2
    source_tex=next(u for u in (i["math"][0]["latex"] for i in
        __import__("build_independent_log_limit_final_qa").UNITS if i["math"])
        if r"o(x^3)-x" in u)
    for cue in actions[0]["emphasis_cues"]:
        assert cue["source_object_id"]=="m_substitute"
        assert cue["latex_fragment"] in source_tex
        assert cue["spoken_phrase"] in split_natural_phrases(
            actions[0]["parts"][0]["value"]
        )
    mutated=copy.deepcopy(doc)
    next(e for e in mutated["events"] if e["event_id"]=="e_cancel")["spans"][0]["emphasis_cues"][0]["latex_fragment"]="not in original"
    bad=folder/"spoken_classroom.json"
    bad.write_text(json.dumps(mutated,ensure_ascii=False),encoding="utf-8")
    with pytest.raises(LongboardError,match="EMPHASIS_NOT_SOURCE_BOUND"):
        checked_spoken(bad)


def test_actual_math_audio_window_determines_write_duration():
    chunks=(
        VoiceChunk("text","先看结构","先看结构",b"0"*128,1000,90),
        VoiceChunk("math","x+y","x 加 y",b"1"*128,1000,660),
        VoiceChunk("text","所以结果明确","所以结果明确",b"2"*128,1000,180),
    )
    voice={"stage":{"e_example":(
        VoicedSpan("math","m_example",chunks,930,90),
    )}}
    timings=build_render_schedules(voice,fps=60)["stage"]["e_example"][0]
    assert timings["duration"]==15.5
    assert timings["math_start_delay"]==1.5
    assert timings["math_end_delay"]==12.5
    assert timings["math_end_delay"]-timings["math_start_delay"]==11.0
    assert DEFAULT_VIDEO_FPS==60


def test_readable_teacher_text_and_no_meta_result_heading(sample):
    folder,doc,contract,plan=sample
    for name in ("strategy","knowledge","pitfall","summary"):
        assert BOARD_TEXT_STYLE[name]["font_px"]>=20
    assert BOARD_DETAIL_FONT_PX>=18
    result=next(e for e in plan["events"] if e["event_id"]=="e_conclusion")
    assert not any(b["kind"]=="teacher_note" for b in result["added_blocks"])
    recap=next(e for e in plan["events"] if e["event_id"]=="e_summary")
    assert any(b["kind"]=="teacher_note" and b["heading"]=="归纳总结"
               for b in recap["added_blocks"])


def test_no_early_method_or_formula_omission(sample):
    folder,doc,contract,plan=sample
    events={e["event_id"]:e for e in doc["events"]}
    first="".join(p.get("value",p.get("reading",""))
        for s in events["e_intro"]["spans"] for p in s["parts"])
    assert first.startswith("同学们大家好")
    assert "我们来读一下" not in first
    strategy=events["e_strategy"]["spans"]
    utterance="".join(p.get("value",p.get("reading","")) for s in strategy for p in s["parts"])
    assert utterance.index("低阶表达式")<utterance.index("泰勒展开")
    assert len(doc["events"])==9
    assert events["e_conclusion"]["spans"][-1]["parts"][1]["latex"]==r"L=\frac13"
