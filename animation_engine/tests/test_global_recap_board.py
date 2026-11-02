"""Global recap board: source provenance, no duplicate spoken action, voice timing.

Covers the full pipeline's mathematical planning without invoking LLM/TTS or
rendering. The real media workflow checks that the actual board is visible.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from animation_engine.adaptive_layout import GlyphSize
from animation_engine.persistent_chalkboard import make_chalkboard_plan
from animation_engine.recap_board import (
    RECAP_BOARD_MODULE, recap_animation_budget, select_recap_sources,
)
from animation_engine.spoken_classroom import checked_spoken
from animation_engine.unified_classroom_flow import checked_flow

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from build_final_fresh_trig_limit import build


def test_fixed_recap_replays_real_lesson_formulae_and_pitfall(tmp_path):
    root=tmp_path/"fresh"
    raw=build(root)
    flow=checked_flow(root/"unified_flow.json")
    stage=flow.stages[0]
    board=make_chalkboard_plan(
        stage.storyboard,stage.execution,stage.cues,stage.policy,
        measure=lambda latex,height: GlyphSize(220,42),
    )
    summary=board["events"][-1]
    assert summary["event_id"]=="e_summary"
    assert summary["recap_board_module"]==RECAP_BOARD_MODULE
    assert summary["erase_before"] is True
    replay=[b for b in summary["added_blocks"] if b.get("recap_review")]
    # Both transferable facts and the previously-authored correction formula
    # are already source-bound in the teaching package, never invented here.
    assert [b["block_id"] for b in replay if b["kind"]=="math"]==[
        "m_sine","m_cosine","m_pitfall",
    ]
    assert any(b["phase"]=="pitfall" and "易错点" in b["heading"]
               for b in replay if b["kind"]=="teacher_note")
    assert all(b.get("carry") is True for b in replay)
    assert summary["math_write_count"]==0
    assert "m_conclusion" not in summary["visible_block_ids"]
    assert summary["recap_review_source_ids"]
    # No extra user-facing lesson/math/speech event is created.
    assert len(board["events"])==len(raw["events"])==12
    old=checked_spoken(root/"spoken_classroom.json",adaptive=False)
    assert [e.event_id for e in old.events]==[e["event_id"] for e in board["events"]]
    original_summary=raw["events"][-1]
    assert len(original_summary["spans"])==1
    assert original_summary["spans"][0]["kind"]=="note"


def test_global_recap_source_selector_does_not_guess_missing_formulas():
    previous=[
        {"added_blocks":[{"kind":"teacher_note","block_id":"note:e_k"},
                         {"kind":"math","block_id":"m_k"}]},
        {"added_blocks":[{"kind":"teacher_note","block_id":"note:e_p"},
                         {"kind":"math","block_id":"m_p"}]},
    ]
    cues=[
        {"phase":"knowledge","event_id":"e_k","heading":"知识"},
        {"phase":"pitfall","event_id":"e_p","heading":"易错"},
    ]
    assert select_recap_sources(previous,cues,{"m_k","m_p"})==[
        ("knowledge",cues[0],previous[0]["added_blocks"][0],["m_k"]),
        ("pitfall",cues[1],previous[1]["added_blocks"][0],["m_p"]),
    ]
    assert select_recap_sources(previous,cues,set())==[
        ("pitfall",cues[1],previous[1]["added_blocks"][0],[]),
    ]
    with pytest.raises(ValueError,match="RECAP_SOURCE_CUE_COUNT_MISMATCH"):
        select_recap_sources(previous,cues[:1],{"m_k"})


@pytest.mark.parametrize("duration,count",[
    (14.0,5), (3.0,3), (1.0,4), (.35,7), (None,4),
])
def test_recap_visuals_fit_old_voice_window(duration,count):
    durations=recap_animation_budget(duration,count,fps=60)
    assert len(durations)==count
    assert all(n>=0 for n in durations)
    if duration is not None:
        assert sum(durations)+.32+4/60 <= duration+1e-6 or duration<.32+4/60
