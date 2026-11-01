"""V2.6.2 teacher-owned diagram lifecycle, native measured layout and safety."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))

from build_adaptive_area_lesson import export_adaptive_lesson
from animation_engine.adaptive_layout import GlyphSize
from animation_engine.adaptive_classroom_flow import (
    _stage_plan, checked_adaptive_flow, plan_adaptive_flow,
)
from animation_engine.longboard_plan import LongboardError
from animation_engine.persistent_chalkboard import DIAGRAM_LEFT_X, DIAGRAM_LEFT_WIDTH


def measure(tex, height):
    return GlyphSize(185, 42)


def manifest(root):
    return json.loads((root/"adaptive_layout.json").read_text(encoding="utf-8"))


def write(root, obj):
    (root/"adaptive_layout.json").write_text(
        json.dumps(obj, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("mode,actions,count", [
    ("hold", ["create", "hold"], 2),
    ("hide", ["create", "hide"], 2),
    ("restore", ["create", "hide", "restore"], 3),
])
def test_reviewed_modes_keep_original_math_and_preserve_source(
        tmp_path, mode, actions, count):
    root = tmp_path / mode
    export_adaptive_lesson(root, mode)
    checked = checked_adaptive_flow(root/"adaptive_layout.json")
    planned = plan_adaptive_flow(root/"adaptive_layout.json", measure=measure)
    assert len(checked.flow.stages) == count
    assert planned["stage_count"] == count
    assert planned["page_count"] == sum(x["page_count"] for x in planned["stages"])
    assert [x["global_first_page"] for x in planned["stages"]] == [
        1 + sum(p["page_count"] for p in planned["stages"][:i])
        for i in range(count)
    ]
    assert all(1 <= e["global_page_index"] <= planned["page_count"]
               for e in planned["events"])
    assert planned["mode"] == "adaptive_classroom_layout"
    assert planned["diagram_lifecycle_source_verified"]
    assert planned["mode_change_policy"].startswith("selective_board_wipe")
    assert [s.action for s in checked.stages] == actions
    assert len({x["global_event_id"] for x in planned["events"]}) == planned["event_count"]
    assert all(stage["native_math_size_preserved"] for stage in planned["stages"])
    assert checked.flow.stages[0].special["teacher_reviewed"] is True
    assert checked.flow.stages[0].package["source"]["problem"] == checked.flow.problem


@pytest.mark.parametrize("mode", ["hold", "restore"])
def test_left_column_is_native_mathtex_and_never_intersects_graph_panel(tmp_path, mode):
    root = tmp_path / mode
    export_adaptive_lesson(root, mode)
    checked = checked_adaptive_flow(root/"adaptive_layout.json")
    for stage, spec in zip(checked.flow.stages, checked.stages):
        if spec.layout != "math_left_diagram_right":
            continue
        plan = _stage_plan(stage, spec, measure=measure)
        assert plan["alignment"]["mode"] == "diagram_left_math_right_geometry"
        assert plan["alignment"]["center_x"] < 500
        assert plan["page_count"] >= 1
        for event in plan["events"]:
            for block in event["added_blocks"]:
                assert DIAGRAM_LEFT_X <= block["x"]
                assert block["x"] + block["w"] <= (
                    DIAGRAM_LEFT_X + DIAGRAM_LEFT_WIDTH + .01)


@pytest.mark.parametrize("change,error", [
    ("unreviewed", "ADAPTIVE_INVALID_MANIFEST"),
    ("bad_mode", "ADAPTIVE_INVALID_MANIFEST"),
    ("extra_field", "ADAPTIVE_INVALID_MANIFEST"),
    ("stale_source", "ADAPTIVE_FLOW_SOURCE_MUTATED"),
    ("missing_stage", "ADAPTIVE_STAGE_COVERAGE"),
    ("swapped_order", "ADAPTIVE_STAGE_ORDER_OR_MODE"),
    ("unknown_action", "ADAPTIVE_STAGE_ORDER_OR_MODE"),
    ("no_reason", "ADAPTIVE_MISSING_TEACHING_REASON"),
    ("fake_source", "ADAPTIVE_DIAGRAM_MUST_REVEAL_FROM_SOURCE"),
    ("early_restore", "ADAPTIVE_RESTORE_WITHOUT_SAVED_SOURCE"),
    ("unverified_hold", "ADAPTIVE_HOLD_WITHOUT_VISIBLE_SOURCE"),
    ("wrong_mode", "ADAPTIVE_HOLD_WITHOUT_VISIBLE_SOURCE"),
    ("hide_and_keep_split", "ADAPTIVE_HIDE_NOT_VISIBLE"),
    ("none_but_visible", "ADAPTIVE_NONE_WHILE_DIAGRAM_VISIBLE"),
])
def test_adaptive_contract_rejects_false_graph_memory(tmp_path, change, error):
    root = tmp_path / change
    export_adaptive_lesson(root, "hold")
    data = manifest(root)
    a, b = data["stages"]
    if change == "unreviewed":
        data["teacher_reviewed"] = False
    elif change == "bad_mode":
        data["mode"] = "fabricated_layout"
    elif change == "extra_field":
        data["extra"] = True
    elif change == "stale_source":
        data["source_flow_sha256"] = "0"*64
    elif change == "missing_stage":
        data["stages"].pop()
    elif change == "swapped_order":
        a["stage_id"] = "something_else"
    elif change == "unknown_action":
        b["diagram_action"] = "invent"
    elif change == "no_reason":
        b["teaching_reason"] = ""
    elif change == "fake_source":
        a["diagram_source_stage"] = "some_other_stage"
    elif change == "early_restore":
        b["diagram_action"] = "restore"
    elif change == "unverified_hold":
        b["diagram_source_stage"] = "different_math_question"
    elif change == "wrong_mode":
        b["layout"] = "full_width"
    elif change == "hide_and_keep_split":
        b["diagram_action"] = "hide"
    elif change == "none_but_visible":
        b["diagram_action"] = "none"
        b["layout"] = "full_width"
        b["diagram_source_stage"] = None
    write(root, data)
    with pytest.raises(LongboardError, match=error):
        checked_adaptive_flow(root/"adaptive_layout.json")


def test_restore_requires_prior_hidden_state(tmp_path):
    root = tmp_path/"restore"
    export_adaptive_lesson(root, "restore")
    data = manifest(root)
    data["stages"][1]["diagram_action"] = "hold"
    data["stages"][1]["layout"] = "math_left_diagram_right"
    write(root, data)
    with pytest.raises(LongboardError, match="ADAPTIVE_RESTORE_WITHOUT_SAVED_SOURCE"):
        checked_adaptive_flow(root/"adaptive_layout.json")


def test_render_args_do_not_accept_invalid_frame_rates(tmp_path):
    from animation_engine.adaptive_classroom_flow import render_adaptive_flow
    with pytest.raises(LongboardError, match="ADAPTIVE_RENDER_ARGUMENTS"):
        render_adaptive_flow(tmp_path/"missing.json",
                             output_mp4=tmp_path/"out.mp4",
                             output_json=tmp_path/"out.json", fps=0)
