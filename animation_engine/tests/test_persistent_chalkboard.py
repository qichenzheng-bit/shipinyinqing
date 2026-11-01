"""Classroom invariants: once written, visible ink never moves/disappears until erase."""
import sys
from pathlib import Path
from collections import Counter
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))

from build_persistent_chalkboard_example import build, main as make_source
from animation_engine.persistent_chalkboard import make_chalkboard_plan
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.longboard_plan import LongboardError
from animation_engine.board_motion import overlaps


def example():
    _, board, execution, cues, policy=build()
    policy.update({
        "guidance_style":"persistent_chalkboard",
        "cut_before_events":[],
        "allow_scroll":False,
        "max_scrolls_per_page":0,
        "pinned_ids":[],
    })
    return board,execution,cues,policy


def test_board_fills_and_erases_only_at_teacher_event_boundary():
    board,execution,cues,policy=example()
    p=make_chalkboard_plan(
        board,execution,cues,policy,
        measure=lambda latex,h: GlyphSize(205,45)
    )
    assert p["event_count"]==14
    assert p["page_count"]>=2
    assert p["mode"]=="persistent_chalkboard"
    assert sum(e["erase_before"] for e in p["events"])==p["page_count"]-1
    assert all(e["page_index"]>1 for e in p["events"] if e["erase_before"])
    assert "m_final" in p["math_written_ids"]
    assert "m_jresult" in p["math_written_ids"]


def test_every_existing_block_keeps_identical_coordinates_until_erased():
    board,execution,cues,policy=example()
    p=make_chalkboard_plan(
        board,execution,cues,policy,
        measure=lambda latex,h: GlyphSize(190,40)
    )
    live={}
    seen=set()
    for event in p["events"]:
        if event["erase_before"]:
            live={}
        for block in event["added_blocks"]:
            bid=block["block_id"]
            assert bid not in live
            for old in live.values():
                assert not overlaps(block,old,margin=0)
            live[bid]=block
            seen.add(bid)
        assert list(live)==event["visible_block_ids"]
        assert all(b["y"]>=148 and b["y"]+b["h"]<=620 for b in live.values())
    assert any(mid.startswith("note:") for mid in seen)


def test_no_auto_erasure_when_full_board_is_not_reached():
    board,execution,cues,policy=example()
    # small enough for short segments, still enough teacher text for >1 page;
    # crucially never cut simply because a new lesson stage starts.
    p=make_chalkboard_plan(
        board,execution,cues,policy,
        measure=lambda latex,h: GlyphSize(140,20)
    )
    for prior,current in zip(p["events"],p["events"][1:]):
        if not current["erase_before"]:
            assert current["page_index"]==prior["page_index"]
            assert set(prior["visible_block_ids"]).issubset(
                current["visible_block_ids"]
            )


def test_refuse_forced_cuts_and_unapproved_teacher_cues():
    board,execution,cues,policy=example()
    bad=dict(policy,cut_before_events=["e_back"])
    with pytest.raises(LongboardError,match="FORCED_CUT"):
        make_chalkboard_plan(
            board,execution,cues,bad,
            measure=lambda latex,h:GlyphSize(180,36))
    broken=dict(cues)
    broken["source_storyboard_sha256"]="0"*64
    with pytest.raises(LongboardError,match="SOURCE_HASH"):
        make_chalkboard_plan(
            board,execution,broken,policy,
            measure=lambda latex,h:GlyphSize(180,36))


def test_example_file_export(tmp_path):
    make_source(tmp_path)
    assert (tmp_path/"storyboard.json").is_file()
    assert (tmp_path/"execution.json").is_file()
    assert (tmp_path/"page_policy.json").is_file()
