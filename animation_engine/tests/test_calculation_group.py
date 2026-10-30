"""2.5.1 source-bound continuous calculation regression tests.

Use the real, independently authored 2.4 integral lesson and an injected glyph
measurer. Planning tests do not claim real MathTex render or audio alignment.
"""
from __future__ import annotations

import copy
import json
import runpy
from pathlib import Path

import pytest

from visual_director.director import build_storyboard
from animation_engine.adaptive_layout import GlyphSize, _overlap
from animation_engine.calculation_group_models import validate_calculation_overlay
from animation_engine.calculation_group_plan import build_calculation_group_plan
from animation_engine.longboard_plan import LongboardError
from animation_engine.planner import build_execution_plan


ROOT = Path(__file__).resolve().parents[2]
NEW_QUESTION = ROOT / "animation_engine" / "tools" / "build_fresh_integral_acceptance.py"
OVERLAY_SCRIPT = ROOT / "animation_engine" / "tools" / "build_fresh_integral_group_overlay.py"


def fake_measure(latex: str, height: int) -> GlyphSize:
    return GlyphSize(width_px=20 + len(latex) * 3.0, height_px=22.0)


@pytest.fixture
def verified_lesson():
    question = runpy.run_path(str(NEW_QUESTION))
    build_overlay = runpy.run_path(str(OVERLAY_SCRIPT))["create_overlay"]
    board = build_storyboard(question["make_package"]())
    execution = build_execution_plan(board)
    overlay = build_overlay(execution)
    return board, execution, overlay


def make_plan(lesson):
    board, execution, overlay = lesson
    return build_calculation_group_plan(
        board, execution, overlay=overlay,
        policy={
            "cut_before_events": ["e_b0", "e_c0", "e_summary"],
            "max_scrolls_per_page": 5, "max_scroll_fraction": 1.0,
        },
        measure=fake_measure,
    )


def test_original_three_part_lesson_has_source_provenance(verified_lesson):
    board, execution, overlay = verified_lesson
    group = validate_calculation_overlay(overlay, execution)
    assert group.approval == "teacher_reviewed"
    assert group.group_kind == "independent_sum"
    assert len(group.parts) == 3
    assert overlay["overview_object_ids"] == ["m_split"]
    assert overlay["final_object_ids"] == ["m_final"]
    assert board.source_package_sha256 == execution.source_package_sha256


def test_three_parts_progress_and_preserve_original_math(verified_lesson):
    plan = make_plan(verified_lesson)
    assert plan["schema_version"] == "2.5.1-preview"
    assert plan["timing_source"] == "preview_only_not_audio_aligned"
    assert plan["calculation_group"]["math_added_or_changed"] is False
    assert len(plan["events"]) == len(verified_lesson[0].scenes)
    by_event = {e["event_id"]: e for e in plan["events"]}
    assert by_event["e_a0"]["group_state"]["active_part_id"] == "integral_1"
    assert by_event["e_a_done"]["group_state"]["phase"] == "part_completed"
    assert by_event["e_a_done"]["group_state"]["completed_part_ids"] == ["integral_1"]
    assert "m_b_done" not in by_event["e_a_done"]["group_state"]["visible_result_ids"]
    assert by_event["e_b0"]["group_state"]["active_part_id"] == "integral_2"
    assert by_event["e_c0"]["group_state"]["active_part_id"] == "integral_3"
    assert by_event["e_summary"]["group_state"]["phase"] == "combine"
    assert by_event["e_final"]["group_state"]["phase"] == "conclusion"

    originals = {
        action.object_id: (action.latex, list(action.source_step_ids))
        for scene in verified_lesson[1].scenes for action in scene.actions
    }
    for row in plan["events"]:
        zone = row["zone_px"]
        for p in row["placements"]:
            assert (p["latex"], p["source_step_ids"]) == originals[p["object_id"]]
            assert p["y"] >= zone[1] + 10
            assert p["y"] + p["h"] <= zone[1] + zone[3] - 10
        for i, a in enumerate(row["placements"]):
            for b in row["placements"][i+1:]:
                assert not _overlap(a, b)
        # No object may be silently skipped when first introduced.
        assert set(row["new_ids"]) <= {
            p["object_id"] for p in row["placements"]
        }


def test_plan_is_deterministic(verified_lesson):
    a, b = make_plan(verified_lesson), make_plan(verified_lesson)
    assert a == b
    assert a["calculation_plan_sha256"] == b["calculation_plan_sha256"]


@pytest.mark.parametrize("corruption,code", [
    (lambda o: o.update(source_execution_sha256="0"*64), "CALC_SOURCE_MISMATCH"),
    (lambda o: o.update(approval="not_reviewed"), "CALC_OVERLAY_INVALID"),
    (lambda o: o["parts"][0]["result_object_ids"].append("unknown"), "CALC_UNKNOWN_OBJECT"),
    (lambda o: o["parts"][0]["result_object_ids"].append("m_b_done"), "CALC_PREMATURE_RESULT"),
    (lambda o: o["parts"][1].update(intro_event_id="e_a0"), "CALC_PART_ORDER"),
    (lambda o: o.update(group_kind="conditional_cases"), "CALC_NON_SUM_COMBINATION_UNSUPPORTED"),
])
def test_invalid_overlay_never_reaches_render(verified_lesson, corruption, code):
    _, execution, approved = verified_lesson
    broken = copy.deepcopy(approved)
    corruption(broken)
    with pytest.raises(LongboardError, match=code):
        validate_calculation_overlay(broken, execution)


def test_dependent_chain_does_not_force_sum_layout(verified_lesson):
    _, execution, approved = verified_lesson
    variant = copy.deepcopy(approved)
    variant["group_kind"] = "dependent_chain"
    variant["combine_event_ids"] = []
    variant["final_object_ids"] = []
    variant["parts"][1]["dependency_part_ids"] = ["integral_1"]
    check = validate_calculation_overlay(variant, execution)
    assert check.group_kind == "dependent_chain"


def test_plan_cli_rejects_stale_overlay_without_writing(tmp_path, verified_lesson):
    from animation_engine.cli import main

    board, execution, overlay = verified_lesson
    bad = copy.deepcopy(overlay)
    bad["source_execution_sha256"] = "f" * 64
    inputs = [
        (tmp_path / "board.json", board.model_dump(mode="json")),
        (tmp_path / "execution.json", execution.model_dump(mode="json")),
        (tmp_path / "overlay.json", bad),
    ]
    for path, value in inputs:
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "bad-plan.json"
    assert main([
        "plan-calculation",
        "--storyboard", str(inputs[0][0]),
        "--execution", str(inputs[1][0]),
        "--overlay", str(inputs[2][0]),
        "--output", str(output),
    ]) == 2
    assert not output.exists()
