"""Second-pass storyboard contract and lifecycle regression tests."""
import copy
import hashlib
import json
import pytest
from visual_director import DirectorError, DirectorOptions, build_storyboard


def test_archived_object_highlight_does_not_silently_reappear(teacher_package):
    last = teacher_package["lesson"]["board_actions"][-1]
    last["math_object_id"] = "m_orient"
    last["action"] = "highlight"
    board = build_storyboard(teacher_package, DirectorOptions(max_visible_formulas=2))
    scene = board.scenes[-1]
    assert any(a.kind == "restore" and a.object_id == "m_orient" for a in scene.actions)


def test_changing_teacher_math_with_old_content_digest_is_rejected(teacher_package):
    teacher_package["validated_content_sha256"] = hashlib.sha256(json.dumps(
        teacher_package, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    board = build_storyboard(teacher_package)
    assert board.source_package_sha256
    teacher_package["lesson"]["math_objects"][1]["latex"] = "unvalidated"
    with pytest.raises(DirectorError, match="PACKAGE_HASH_MISMATCH"):
        build_storyboard(teacher_package)


def test_canonical_source_hash_is_independent_of_json_key_order(teacher_package):
    teacher_package["source"] = dict(reversed(list(teacher_package["source"].items())))
    assert build_storyboard(teacher_package).header.text


def test_teacher_example_source_steps_have_verified_quotes(teacher_package):
    source = teacher_package["source"]["solution_segments"]
    corpus = {s["source_id"]: s["text"] for s in source}
    for step in teacher_package["understanding"]["solution_steps"]:
        if step["origin"] == "source":
            for source_id in step["source_refs"]:
                if source_id in corpus:
                    assert step.get("source_quotes", {}).get(source_id) in corpus[source_id]
