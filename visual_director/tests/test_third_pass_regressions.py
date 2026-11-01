"""Regression: visible objects must not reference regions absent from a scene."""
from visual_director import build_storyboard


def test_scratch_object_highlight_after_full_board_switch_has_valid_region(teacher_package):
    # The knowledge equation exists on the scratch side in the preceding scene.
    # The next derivation refers to that *existing* equation, rather than
    # writing a new mathematical object.
    action = next(
        a for a in teacher_package["lesson"]["board_actions"]
        if a["event_id"] == "e_d_log"
    )
    action["math_object_id"] = "m_k_log"
    action["action"] = "highlight"

    scenes = build_storyboard(teacher_package).scenes
    knowledge_scene = next(s for s in scenes if s.event_id == "e_k_log")
    derivation_scene = next(s for s in scenes if s.event_id == "e_d_log")

    assert knowledge_scene.object_regions["m_k_log"] == "scratch"
    assert derivation_scene.layout == "full_board"
    assert "m_k_log" in derivation_scene.visible_ids
    assert derivation_scene.object_regions["m_k_log"] in derivation_scene.regions
    assert derivation_scene.object_regions["m_k_log"] == "board"
