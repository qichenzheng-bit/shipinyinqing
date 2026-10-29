import copy
import json
import pytest

from visual_director import DirectorOptions, DirectorError, build_storyboard
from visual_director.models import DiagramSpec, DiagramPoint, DiagramLine


def test_full_limit_sample_is_deterministic_and_preserves_reference(teacher_package):
    first = build_storyboard(teacher_package)
    second = build_storyboard(teacher_package)
    assert first.model_dump_json() == second.model_dump_json()
    assert len(first.scenes) == 19
    assert first.header.text == teacher_package["source"]["problem"]
    assert first.header.position == "top_fixed"
    assert first.header.align == "center"
    assert first.theme.background == "#FFFFFF"
    assert first.captions[0].speech_unit_id == "u_read"
    assert any(p.kind == "math" and "\\lim" in p.value for p in first.captions[0].parts)
    assert not hasattr(first.captions[0], "reading_intent")
    assert first.scenes[-1].event_id == "e_end"
    assert all(s.regions["board"].y + s.regions["board"].h <= s.regions["captions"].y for s in first.scenes)
    assert not any("boxed" in a.latex for s in first.scenes for a in s.actions)


def test_knowledge_uses_adjacent_work_area_without_covering_header(teacher_package):
    board = build_storyboard(teacher_package)
    s = next(x for x in board.scenes if x.event_id == "e_k_log")
    assert s.layout == "split_scratch"
    assert s.regions["scratch"].x > s.regions["board"].x
    assert s.regions["board"].y >= board.header.height


def test_bad_reference_rejected_before_planning(teacher_package):
    teacher_package["lesson"]["board_actions"][1]["math_object_id"] = "fake_math"
    with pytest.raises(DirectorError, match="UNKNOWN_MATH_OBJECT"):
        build_storyboard(teacher_package)


def test_future_math_is_not_visible_earlier(teacher_package):
    storyboard = build_storyboard(teacher_package)
    final_obj = teacher_package["lesson"]["board_actions"][-1]["math_object_id"]
    assert all(final_obj not in scene.visible_ids for scene in storyboard.scenes[:-1])
    assert final_obj in storyboard.scenes[-1].visible_ids


def test_unverified_math_package_rejected_unless_opted_in(teacher_package):
    teacher_package["validation"]["status"] = "needs_review"
    with pytest.raises(DirectorError, match="NEEDS_REVIEW"):
        build_storyboard(teacher_package)
    board = build_storyboard(teacher_package, DirectorOptions(allow_needs_review=True))
    assert "NEEDS_REVIEW" in board.warnings
    teacher_package["validation"]["status"] = "blocked"
    with pytest.raises(DirectorError, match="BLOCKED_PACKAGE"):
        build_storyboard(teacher_package, DirectorOptions(allow_needs_review=True))


def test_source_caption_must_equal_spoken_semantics(teacher_package):
    teacher_package["subtitles"][0]["parts"][0]["value"] = "another speech"
    with pytest.raises(DirectorError, match="CAPTION_MISMATCH"):
        build_storyboard(teacher_package)


def test_math_captions_preserve_latex_and_separate_from_tts(teacher_package):
    result = build_storyboard(teacher_package)
    speaker_unit = teacher_package["lesson"]["speech_units"][0]
    assert result.captions[0].parts[1].value == speaker_unit["parts"][1]["value"]
    assert result.captions[0].parts[1].kind == "math"
    assert "reading_intent" not in result.captions[0].model_dump_json()
    assert all(c.start_second is None for c in result.captions)


def test_long_question_left_align_and_never_covered(teacher_package):
    teacher_package["source"]["problem"] = "条件：" + "当 x 趋于零时，" * 35 + "求极限。"
    result = build_storyboard(teacher_package)
    assert result.header.align == "left"
    assert result.header.lines > 1
    assert result.header.height < .38
    for scene in result.scenes:
        assert scene.regions["board"].y >= result.header.height


def test_matrix_keeps_old_and_new_states(teacher_package):
    act = teacher_package["lesson"]["board_actions"][1]
    math_id = act["math_object_id"]
    obj = next(x for x in teacher_package["lesson"]["math_objects"] if x["math_object_id"] == math_id)
    obj["latex"] = r"\begin{pmatrix}1&2\\2&5\end{pmatrix}"
    act2 = teacher_package["lesson"]["board_actions"][2]
    obj2 = next(x for x in teacher_package["lesson"]["math_objects"] if x["math_object_id"] == act2["math_object_id"])
    obj2["latex"] = r"\begin{pmatrix}1&2\\0&1\end{pmatrix}"
    result = build_storyboard(teacher_package)
    scene = result.scenes[2]
    assert scene.layout == "matrix_compare"
    assert math_id in scene.visible_ids
    assert obj2["math_object_id"] in scene.visible_ids


def test_transform_without_mapping_is_safe_fallback(teacher_package):
    act = teacher_package["lesson"]["board_actions"][1]
    act["action"] = "transform"
    result = build_storyboard(teacher_package)
    assert result.scenes[1].actions[0].kind == "progressive_write"
    assert "TRANSFORM_REQUIRES_MAPPING" in result.warnings


def test_diagram_only_when_supplied(teacher_package):
    result = build_storyboard(teacher_package)
    assert all(s.layout != "diagram_split" for s in result.scenes)
    hint = DiagramSpec(event_id="e_d_log", points=[DiagramPoint(id="a",x=.3,y=.4,label="A")],lines=[])
    result = build_storyboard(teacher_package, DirectorOptions(diagrams=[hint]))
    scene = next(s for s in result.scenes if s.event_id == "e_d_log")
    assert scene.layout == "diagram_split"
    assert scene.diagram is not None


def test_diagram_labels_avoid_points_lines_and_each_other(teacher_package):
    d = DiagramSpec(event_id="e_d_log",points=[
        DiagramPoint(id="A",x=.3,y=.5,label="A"),
        DiagramPoint(id="B",x=.7,y=.5,label="B")],
        lines=[DiagramLine(id="AB",start="A",end="B")])
    plan=build_storyboard(teacher_package, DirectorOptions(diagrams=[d]))
    placed=next(s.diagram for s in plan.scenes if s.event_id=="e_d_log")
    assert len(placed.labels)==2
    for lbl in placed.labels:
        assert not (.3 <= lbl.x <= .7 and abs(lbl.y-.5) < .02)


def test_duplicate_or_invalid_diagram_rejected(teacher_package):
    d = DiagramSpec(event_id="e_d_log",points=[DiagramPoint(id="A",x=.3,y=.5,label="A")],lines=[DiagramLine(id="AB",start="A",end="absent")])
    with pytest.raises(DirectorError, match="DIAGRAM_REFERENCE"):
        build_storyboard(teacher_package,DirectorOptions(diagrams=[d]))


def test_long_proof_scroll_and_retains_history(teacher_package):
    for event in teacher_package["plan"]["teaching_events"]:
        if event["event_type"] == "derivation":
            event["event_type"] = "proof"
    result=build_storyboard(teacher_package, DirectorOptions(max_visible_formulas=3))
    assert any(s.layout == "proof_scroll" for s in result.scenes)
    assert result.scenes[-1].archived_ids
    assert len(result.scenes[-1].visible_ids) <= 3
    assert len(set(result.scenes[-1].archived_ids) & set(result.scenes[-1].visible_ids)) == 0


def test_invalid_boxed_answer_blocked(teacher_package):
    final_id=teacher_package["lesson"]["board_actions"][-1]["math_object_id"]
    obj=next(x for x in teacher_package["lesson"]["math_objects"] if x["math_object_id"]==final_id)
    obj["latex"]=r"\boxed{2/3}"
    with pytest.raises(DirectorError,match="BOXED_ANSWER"):
        build_storyboard(teacher_package)


def test_scratch_knowledge_has_region_and_is_archived_when_returning(teacher_package):
    result = build_storyboard(teacher_package)
    explain = next(scene for scene in result.scenes if scene.event_id == "e_k_log")
    apply = next(scene for scene in result.scenes if scene.event_id == "e_app_log")
    back = next(scene for scene in result.scenes if scene.event_id == "e_d_log")
    assert explain.object_regions["m_k_log"] == "scratch"
    assert apply.object_regions["m_app_log"] == "scratch"
    assert "m_k_log" not in back.visible_ids
    assert "m_k_log" in back.archived_ids
    assert back.object_regions["m_d_log"] == "board"


def test_diagram_curve_collision_is_geometrically_checked(teacher_package):
    from visual_director.models import DiagramCurve
    d=DiagramSpec(event_id="e_d_log",points=[DiagramPoint(id="P",x=.5,y=.5,label="P")],
        lines=[],curves=[DiagramCurve(id="horizontal",points=[(0.05,.5),(.95,.5)])])
    storyboard=build_storyboard(teacher_package,DirectorOptions(diagrams=[d]))
    label=next(s.diagram.labels[0] for s in storyboard.scenes if s.event_id=="e_d_log")
    assert not(label.y<.5<label.y+label.h)


def test_no_title_inference_for_probability_without_explicit_diagram(teacher_package):
    teacher_package["understanding"]["problem_understanding"]["problem_type"]="概率统计"
    director=build_storyboard(teacher_package)
    assert all(s.diagram is None for s in director.scenes)


def test_reuse_of_archived_object_restores_without_math_rewriting(teacher_package):
    last = teacher_package["lesson"]["board_actions"][-1]
    last["math_object_id"] = "m_orient"
    last["action"] = "retain"
    result=build_storyboard(teacher_package,DirectorOptions(max_visible_formulas=3))
    assert "m_orient" in result.scenes[-1].visible_ids
    assert "m_orient" not in result.scenes[-1].archived_ids
    assert result.scenes[-1].actions[0].latex == next(o["latex"] for o in teacher_package["lesson"]["math_objects"] if o["math_object_id"] == "m_orient")


def test_long_knowledge_formula_uses_full_width_to_prevent_squeeze(teacher_package):
    math_id = next(a["math_object_id"] for a in teacher_package["lesson"]["board_actions"] if a["event_id"] == "e_k_log")
    next(o for o in teacher_package["lesson"]["math_objects"] if o["math_object_id"] == math_id)["latex"] = r"\lim_{x\to0}\frac{(1+\int_0^x\sin t\,dt)(\ln(1+x^2)+\sin^2x)}{\ln(1+x^2)\sin^2x}+\int_0^1\frac{\sin t}{1+t^2}\,dt"
    scene = next(s for s in build_storyboard(teacher_package).scenes if s.event_id=="e_k_log")
    assert scene.layout == "full_board"
    assert "scratch" not in scene.regions


def test_long_caption_is_preserved_not_arbitrarily_truncated(teacher_package):
    text = "请注意这个条件，" * 45
    teacher_package["lesson"]["speech_units"][0]["parts"][0]["value"] = text
    teacher_package["subtitles"][0]["parts"][0]["value"] = text
    storyboard=build_storyboard(teacher_package)
    assert storyboard.captions[0].parts[0].value==text
    assert storyboard.timing == "semantic_anchors_only"


def test_animation_intents_have_known_event_and_action_references(teacher_package):
    teacher_package["lesson"]["animation_intents"][0]["board_action_ids"]=["not-real"]
    with pytest.raises(DirectorError,match="ANIMATION_REFERENCE"):
        build_storyboard(teacher_package)


def test_missing_event_membership_for_voice_unit_is_rejected(teacher_package):
    teacher_package["lesson"]["lesson_events"][0]["speech_unit_ids"]=[]
    with pytest.raises(DirectorError,match="SPEECH_REFERENCE"):
        build_storyboard(teacher_package)


def test_all_visual_actions_keep_semantic_voice_anchor(teacher_package):
    board=build_storyboard(teacher_package)
    teacher_ids={u["speech_unit_id"] for u in teacher_package["lesson"]["speech_units"]}
    assert all(action.speech_unit_id in teacher_ids and action.anchor=="speech_unit" for scene in board.scenes for action in scene.actions)


def test_read_question_highlights_fixed_header_without_duplicate_math(teacher_package):
    result = build_storyboard(teacher_package)
    first = result.scenes[0]
    assert first.actions[0].kind == "brief_highlight"
    assert "m_read" not in first.visible_ids
    assert "HIGHLIGHT_UNSEEN_DOWNGRADED" not in result.warnings