"""V1 storyboard safety regressions, independent of Manim and TTS."""
import copy
import hashlib
import json
import pytest
from visual_director import DirectorError, DirectorOptions, DiagramSpec, DiagramPoint, DiagramCurve, build_storyboard


def _refresh_source_hash(package):
    package["input_sha256"] = hashlib.sha256(
        json.dumps(package["source"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize("action", ["retain", "group"])
def test_unseen_retain_or_group_is_not_a_write(teacher_package, action):
    teacher_package["lesson"]["board_actions"][1]["action"] = action
    with pytest.raises(DirectorError, match="UNSEEN_OBJECT_ACTION"):
        build_storyboard(teacher_package)


def test_archiving_emits_explicit_action_for_renderer(teacher_package):
    plan = build_storyboard(teacher_package, DirectorOptions(max_visible_formulas=2))
    assert any(action.kind == "archive" for scene in plan.scenes for action in scene.actions)
    for scene in plan.scenes:
        assert all(a.object_id in scene.archived_ids for a in scene.actions if a.kind == "archive")


def test_retain_of_archived_formula_emits_restore(teacher_package):
    last = teacher_package["lesson"]["board_actions"][-1]
    last["math_object_id"] = "m_orient"
    last["action"] = "retain"
    plan = build_storyboard(teacher_package, DirectorOptions(max_visible_formulas=2))
    assert any(a.kind == "restore" and a.object_id == "m_orient"
               for a in plan.scenes[-1].actions)


def test_mutating_source_with_old_hash_is_rejected(teacher_package):
    teacher_package["source"]["problem"] += "伪造附加题干"
    with pytest.raises(DirectorError, match="SOURCE_HASH_MISMATCH"):
        build_storyboard(teacher_package)


def test_correctly_rehashed_source_still_supported(teacher_package):
    teacher_package["source"]["problem"] += " 附加有效条件。"
    _refresh_source_hash(teacher_package)
    assert build_storyboard(teacher_package).header.text.endswith("附加有效条件。")


def test_duplicate_caption_for_one_speech_unit_is_rejected(teacher_package):
    duplicate = copy.deepcopy(teacher_package["subtitles"][0])
    duplicate["subtitle_id"] = "extra-subtitle-id"
    teacher_package["subtitles"].append(duplicate)
    with pytest.raises(DirectorError, match="CAPTION_DUPLICATE_SPEECH"):
        build_storyboard(teacher_package)


def test_short_curve_inside_large_label_does_not_pass_sampling_gap(teacher_package):
    spec = DiagramSpec(event_id="e_d_log", points=[
        DiagramPoint(id="P", x=.4, y=.5, label="ABCDEFGHIJKLMNO")
    ], curves=[DiagramCurve(id="curve", points=[(.49,.43),(.50,.43)])])
    plan = build_storyboard(teacher_package, DirectorOptions(diagrams=[spec]))
    label = next(scene.diagram.labels[0] for scene in plan.scenes if scene.event_id == "e_d_log")
    assert not(label.x <= .495 <= label.x + label.w
               and label.y <= .43 <= label.y + label.h)
