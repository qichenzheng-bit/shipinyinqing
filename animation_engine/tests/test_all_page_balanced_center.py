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
def test_each_full_page_is_balanced_vertically_without_reposition(variant):
    _,board,execution,cues,policy,manifest,_,_,_=build_variant(variant)
    plan = make_chalkboard_plan(board, execution, cues, policy,
                                measure=measure, computation_manifest=manifest)
    assert plan["alignment"]["mode"]=="each_unit_centered_with_page_vertical_balance"
    for page in plan["alignment"]["pages"]:
        assert abs(page["ink_center_x"] - BOARD_CENTER_X) < 1
        assert abs(page["ink_center_y"] - BOARD_CENTER_Y) < 1
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
    assert all(abs(p["ink_center_y"]-BOARD_CENTER_Y)<1
               for p in plan["alignment"]["pages"])
