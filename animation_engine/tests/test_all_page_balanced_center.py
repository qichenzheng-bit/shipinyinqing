"""Balanced center on EVERY board page, not only on the final screen.

The layout is finalized before rendering. Existing visible MathTex and
teaching notes must keep the same coordinates throughout each page.
"""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
from build_multipart_integral_lesson import build_variant
from build_complete_ode_lesson import build_new
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.board_motion import overlaps
from animation_engine.persistent_chalkboard import (
    make_chalkboard_plan, _ink_width, BOARD_CENTER_X, BOARD_CENTER_Y,
    BOARD_START_Y, BOARD_BOTTOM_Y, BOARD_X, BOARD_WIDTH,
    QUESTION_TO_BOARD_MIN_GAP_PX, MAX_PAGE_TOP_OFFSET_PX,
)


def measure(latex, height):
    return GlyphSize(240, 42)


@pytest.mark.parametrize("variant", ["A", "B", "C"])
def test_each_math_teaching_unit_is_centered_not_only_final(variant):
    _, board, execution, cues, policy, manifest, _, _, _ = build_variant(variant)
    plan = make_chalkboard_plan(board, execution, cues, policy,
                                measure=measure, computation_manifest=manifest)
    for event in plan["events"]:
        blocks = [b for b in event["added_blocks"] if not b.get("carry")]
        assert blocks, event["event_id"]
        left = min(b["x"] for b in blocks)
        right = max(b["x"] + _ink_width(b) for b in blocks)
        assert abs((left + right)/2 - BOARD_CENTER_X) < 1, event["event_id"]
        for block in blocks:
            assert BOARD_X <= block["x"] < BOARD_X + BOARD_WIDTH
            assert block["x"] + _ink_width(block) <= BOARD_X + BOARD_WIDTH + 0.01


@pytest.mark.parametrize("variant", ["A", "B", "C"])
def test_each_page_starts_near_the_question_without_reposition(variant):
    _,board,execution,cues,policy,manifest,_,_,_=build_variant(variant)
    plan = make_chalkboard_plan(board, execution, cues, policy,
                                measure=measure, computation_manifest=manifest)
    assert plan["alignment"]["mode"]=="each_unit_centered_with_header_near_top"
    for page in plan["alignment"]["pages"]:
        assert abs(page["ink_center_x"] - BOARD_CENTER_X) < 1
        assert (plan["coordinates"]["start_y"] <= page["first_ink_y"]
                <= plan["alignment"]["max_first_ink_y"])
        assert page["vertical_offset_px"] <= MAX_PAGE_TOP_OFFSET_PX
        assert (QUESTION_TO_BOARD_MIN_GAP_PX <= page["header_to_ink_gap_px"]
                <= plan["alignment"]["max_first_ink_y"]-page["header_bottom_y"])
    live = {}
    for event in plan["events"]:
        if event["erase_before"]:
            live = {}
        for block in event["added_blocks"]:
            assert block["block_id"] not in live
            assert BOARD_START_Y-0.01 <= block["y"]
            assert block["y"]+block["h"] <= BOARD_BOTTOM_Y + 0.01
            assert not any(overlaps(block, old, margin=0) for old in live.values())
            live[block["block_id"]] = block
            if block["kind"] == "math":
                # Rendered MathTex fragments receive precisely the same translation.
                assert block["fragments"]
                assert abs(block["fragments"][0]["x"] - block["x"]) < 0.01
                assert abs(block["fragments"][0]["y"] - block["y"]) < 0.01
        assert list(live) == event["visible_block_ids"]
    assert plan["page_count"] == len(plan["alignment"]["pages"])


def test_general_non_integral_teaching_is_also_centered():
    _,board,execution,cues,policy = build_new()
    plan = make_chalkboard_plan(board, execution, cues, policy, measure=measure)
    for row in plan["events"]:
        blocks = row["added_blocks"]
        left = min(b["x"] for b in blocks)
        right = max(b["x"]+_ink_width(b) for b in blocks)
        if row["erase_before"] and len(blocks)>1:
            # The re-written carry and new unit are each centered separately.
            fresh = [b for b in blocks if not b.get("carry")]
            assert fresh
            left = min(b["x"] for b in fresh)
            right = max(b["x"]+_ink_width(b) for b in fresh)
        assert abs((left+right)/2-BOARD_CENTER_X) < 1
    assert all(p["first_ink_y"]<=plan["alignment"]["max_first_ink_y"]
               for p in plan["alignment"]["pages"])


def test_sparse_last_page_does_not_drop_the_final_answer_far_below_question():
    # The exact regression: the final page has little ink and the old
    # unconditional y-centering would create a wide empty band under the stem.
    _,board,execution,cues,policy,manifest,_,_,_ = build_variant("C")
    layout=make_chalkboard_plan(board,execution,cues,policy,
                               measure=measure,computation_manifest=manifest)
    last=layout["events"][-1]
    assert last["page_index"]==layout["page_count"]
    page=next(p for p in layout["alignment"]["pages"]
              if p["page_index"]==last["page_index"])
    assert page["first_ink_y"]<=layout["alignment"]["max_first_ink_y"]
    assert page["header_to_ink_gap_px"] <= 55
    assert abs(page["ink_center_x"]-BOARD_CENTER_X)<1


def test_sparse_page_header_gap_has_both_minimum_and_maximum():
    from animation_engine.persistent_chalkboard import _center_page_heights
    blocks=[{"kind":"math","block_id":"a",
             "x":600.0,"y":148.0,"w":80.0,"h":35.0,
             "fragments":[{"x":600.0,"y":148.0,"w":80.0,"h":35.0}]}]
    event={"page_index":1,"added_blocks":blocks}
    pages=_center_page_heights([event],page_start_y=148,header_bottom_y=119)
    assert pages[0]["first_ink_y"]==148+MAX_PAGE_TOP_OFFSET_PX
    assert pages[0]["header_to_ink_gap_px"]==49
    assert blocks[0]["y"]==blocks[0]["fragments"][0]["y"]


def test_tall_question_reserves_its_full_header_before_starting_ink():
    from animation_engine.persistent_chalkboard import _page_start_y
    from types import SimpleNamespace
    region=SimpleNamespace(y=0.01,h=0.28)
    board=SimpleNamespace(scenes=[SimpleNamespace(regions={"question":region})])
    start,bottom=_page_start_y(board)
    assert bottom==209
    assert start==bottom+QUESTION_TO_BOARD_MIN_GAP_PX
