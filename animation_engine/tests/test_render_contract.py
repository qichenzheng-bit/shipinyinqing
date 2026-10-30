"""Read-only, provenance-preserving input selection for the MathTex renderer."""
import json
from pathlib import Path

import pytest
from visual_director import build_storyboard
from animation_engine import build_execution_plan
from animation_engine.render_contract import RenderContractError, select_math_render_request


SAMPLE = Path(__file__).resolve().parents[2] / "visual_director" / "examples" / "limit_teaching_package.json"


@pytest.fixture
def inputs():
    storyboard = build_storyboard(json.loads(SAMPLE.read_text(encoding="utf-8")))
    execution = build_execution_plan(storyboard)
    return storyboard, execution


def _visible_formula(storyboard, execution):
    for scene in execution.scenes:
        for action in scene.actions:
            if action.kind == "progressive_write" and action.object_id in scene.visible_ids:
                return scene.event_id, action.object_id, action
    raise AssertionError("fixture has no board formula")


def test_select_visible_formula_preserves_latex_region_and_provenance(inputs):
    storyboard, execution = inputs
    eid, oid, original = _visible_formula(storyboard, execution)
    original_story = storyboard.model_dump(mode="json")
    original_exec = execution.model_dump(mode="json")
    req = select_math_render_request(storyboard, execution, event_id=eid, object_id=oid)
    scene = next(s for s in storyboard.scenes if s.event_id == eid)
    assert (req.event_id, req.object_id, req.latex) == (eid, oid, original.latex)
    assert req.region == scene.regions[scene.object_regions[oid]]
    assert req.region_name == scene.object_regions[oid]
    assert req.source_step_ids == tuple(original.source_step_ids)
    assert req.source_storyboard_sha256 == execution.source_storyboard_sha256
    assert storyboard.model_dump(mode="json") == original_story
    assert execution.model_dump(mode="json") == original_exec


def test_reject_stale_storyboard_hash(inputs):
    storyboard, execution = inputs
    eid, oid, _ = _visible_formula(storyboard, execution)
    execution.source_storyboard_sha256 = "0" * 64
    with pytest.raises(RenderContractError, match="MISMATCH_EXECUTION_PLAN"):
        select_math_render_request(storyboard, execution, event_id=eid, object_id=oid)


def test_reject_tampered_execution_actions_even_if_digest_matches(inputs):
    storyboard, execution = inputs
    eid, oid, _ = _visible_formula(storyboard, execution)
    execution.scenes[1].actions[0].latex = "x=999"
    with pytest.raises(RenderContractError, match="MISMATCH_EXECUTION_PLAN"):
        select_math_render_request(storyboard, execution, event_id=eid, object_id=oid)


def test_reject_header_highlight_only(inputs):
    storyboard, execution = inputs
    first = execution.scenes[0]
    assert first.actions[0].to_region == "question"
    with pytest.raises(RenderContractError, match="NOT_VISIBLE_BOARD_OBJECT"):
        select_math_render_request(storyboard, execution, event_id=first.event_id,
                                   object_id=first.actions[0].object_id)


def test_reject_unknown_event_and_invisible_object(inputs):
    storyboard, execution = inputs
    eid, oid, _ = _visible_formula(storyboard, execution)
    with pytest.raises(RenderContractError, match="UNKNOWN_EVENT"):
        select_math_render_request(storyboard, execution, event_id="missing", object_id=oid)
    with pytest.raises(RenderContractError, match="NOT_VISIBLE_BOARD_OBJECT"):
        select_math_render_request(storyboard, execution, event_id=eid, object_id="missing")


def test_reject_malformed_execution_without_state_change(inputs):
    storyboard, execution = inputs
    eid, oid, _ = _visible_formula(storyboard, execution)
    bad = execution.model_dump(mode="json")
    bad["scenes"][0]["state_sha256"] = "corrupt"
    with pytest.raises(RenderContractError, match="MISMATCH_EXECUTION_PLAN"):
        select_math_render_request(storyboard, bad, event_id=eid, object_id=oid)
