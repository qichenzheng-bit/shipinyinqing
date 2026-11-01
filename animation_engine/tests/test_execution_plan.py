"""Contract and deterministic lifecycle regression tests for animation-engine V1 step 1."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from visual_director import build_storyboard
from animation_engine import ExecutionError, build_execution_plan


SAMPLE = Path(__file__).resolve().parents[2] / "visual_director" / "tests" / "fixtures" / "limit_teaching_package.json"


@pytest.fixture
def storyboard():
    return build_storyboard(json.loads(SAMPLE.read_text(encoding="utf-8")))


def test_real_storyboard_compiles_in_order_and_matches_each_snapshot(storyboard):
    result = build_execution_plan(storyboard)
    assert result.schema_version == "1.0"
    assert result.sync_status == "semantic_anchors_only"
    assert result.source_package_sha256 == storyboard.source_package_sha256
    assert len(result.scenes) == len(storyboard.scenes) == 19
    for planned, scene in zip(storyboard.scenes, result.scenes):
        assert scene.event_id == planned.event_id
        assert [a.action_id for a in scene.actions] == [a.action_id for a in planned.actions]
        assert scene.visible_ids == planned.visible_ids
        assert scene.archived_ids == planned.archived_ids
        assert scene.object_regions == planned.object_regions
        assert len(scene.state_sha256) == 64


def test_question_highlight_is_header_only_not_a_new_board_object(storyboard):
    first = build_execution_plan(storyboard).scenes[0]
    assert first.actions[0].kind == "brief_highlight"
    assert first.actions[0].to_region == "question"
    assert first.actions[0].after == "absent"
    assert "m_read" not in first.visible_ids


def test_deterministic_json_and_input_untouched(storyboard):
    original = storyboard.model_dump(mode="json")
    left = build_execution_plan(storyboard).model_dump_json()
    right = build_execution_plan(storyboard.model_dump(mode="json")).model_dump_json()
    assert left == right
    assert storyboard.model_dump(mode="json") == original


def test_every_action_retains_semantic_anchor_and_math_provenance(storyboard):
    result = build_execution_plan(storyboard)
    candidates = {x.speech_unit_id for x in storyboard.captions}
    for scene in result.scenes:
        for action in scene.actions:
            assert action.speech_unit_id in candidates
            assert action.source_step_ids
            assert action.event_id == scene.event_id
    assert "start_second" not in result.model_dump_json()
    assert "duration" not in result.model_dump_json()


def test_reject_invalid_scene_snapshot(storyboard):
    storyboard.scenes[1].visible_ids = []
    with pytest.raises(ExecutionError, match="SNAPSHOT_MISMATCH"):
        build_execution_plan(storyboard)


def test_reject_missing_visible_region(storyboard):
    storyboard.scenes[1].object_regions["m_orient"] = "scratch"
    with pytest.raises(ExecutionError, match="REGION_REFERENCE"):
        build_execution_plan(storyboard)


def test_reject_duplicate_action_id(storyboard):
    storyboard.scenes[2].actions[0].action_id = storyboard.scenes[1].actions[0].action_id
    with pytest.raises(ExecutionError, match="DUPLICATE_ACTION_ID"):
        build_execution_plan(storyboard)


def test_reject_unknown_speech_anchor(storyboard):
    storyboard.scenes[1].actions[0].speech_unit_id = "unknown-speech"
    with pytest.raises(ExecutionError, match="SPEECH_REFERENCE"):
        build_execution_plan(storyboard)


def test_reject_restore_of_never_created_object(storyboard):
    storyboard.scenes[1].actions[0].kind = "restore"
    with pytest.raises(ExecutionError, match="INVALID_TRANSITION"):
        build_execution_plan(storyboard)


def test_reject_object_id_reused_with_new_formula(storyboard):
    storyboard.scenes[2].actions[0].object_id = "m_orient"
    storyboard.scenes[2].actions[0].latex = "x=999"
    with pytest.raises(ExecutionError, match="OBJECT_ID_CONFLICT"):
        build_execution_plan(storyboard)


def test_archived_formula_restored_before_highlight_and_scratch_relocated():
    package = json.loads(SAMPLE.read_text(encoding="utf-8"))
    act = next(a for a in package["lesson"]["board_actions"] if a["event_id"] == "e_d_log")
    act["math_object_id"] = "m_k_log"
    act["action"] = "highlight"
    storyboard = build_storyboard(package)
    result = build_execution_plan(storyboard)
    derivation = next(s for s in result.scenes if s.event_id == "e_d_log")
    move = next(a for a in derivation.actions if a.object_id == "m_k_log" and a.kind == "retain")
    emphasize = next(a for a in derivation.actions if a.object_id == "m_k_log" and a.kind == "brief_highlight")
    assert move.from_region == "scratch"
    assert move.to_region == "board"
    assert emphasize.before == "visible" and emphasize.after == "visible"
    assert derivation.object_regions["m_k_log"] == "board"


def test_plan_requires_valid_schema(storyboard):
    malformed = storyboard.model_dump(mode="json")
    malformed["schema_version"] = "7.0"
    with pytest.raises(ExecutionError, match="STORYBOARD_SCHEMA"):
        build_execution_plan(malformed)


def test_archived_object_restores_without_rewriting_mathematics():
    from visual_director import DirectorOptions

    package = json.loads(SAMPLE.read_text(encoding="utf-8"))
    last = package["lesson"]["board_actions"][-1]
    last["math_object_id"] = "m_orient"
    last["action"] = "retain"
    storyboard = build_storyboard(package, DirectorOptions(max_visible_formulas=3))
    execution = build_execution_plan(storyboard)
    final_scene = execution.scenes[-1]
    assert any(a.object_id == "m_orient" and a.kind == "restore"
               and a.before == "archived" and a.after == "visible"
               for a in final_scene.actions)
    assert "m_orient" in final_scene.visible_ids
    assert "m_orient" not in final_scene.archived_ids


def test_remove_existing_board_object_clears_registry_state(storyboard):
    scene = storyboard.scenes[1].model_copy(deep=True)
    scene.event_id = "e_remove"
    scene.actions[0].event_id = "e_remove"
    scene.actions[0].action_id = "test:remove:m_orient"
    scene.actions[0].kind = "remove"
    scene.actions[0].source_action = "remove"
    scene.visible_ids = []
    scene.archived_ids = []
    scene.object_regions = {}
    storyboard.scenes = storyboard.scenes[:2] + [scene]

    execution = build_execution_plan(storyboard)
    action = execution.scenes[-1].actions[0]
    assert action.before == "visible" and action.after == "absent"
    assert action.from_region == "board" and action.to_region is None
    assert execution.scenes[-1].visible_ids == []
