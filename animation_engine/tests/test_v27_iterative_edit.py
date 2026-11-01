"""Non-render V2.7 iterative-edit approval and immutable-video regression tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "fixtures"))
from build_novel_substitution_integral import build

from animation_engine.iterative_edit_engine import (
    _state, create_session, run_edit,
)
from animation_engine.spoken_classroom import checked_spoken
from animation_engine.v27_teacher_contract import (
    export_spoken_script, require_prerender_script,
)


def _report(package: Path):
    approved = checked_spoken(package / "spoken_classroom.json", adaptive=False)
    actions = sum(len(event.spans) for event in approved.events)
    return {
        "source_spoken_sha256": approved.source_sha256,
        "source_flow_sha256": approved.flow.source_sha256,
        "voice_status": "real_edge_neural_pcm_verified",
        "subtitle_status": "actual_tts_phrase_aligned",
        "math_caption_renderer": "true_manim_mathtex",
        "voiced_action_count": actions,
        "source_narration_action_count": actions,
        "fabricated_voice_or_subtitle_count": 0,
        "audio_verification": {"sample_rate": 24000, "channels": 1},
    }


def _fake_media(path):
    assert Path(path).is_file()


def _fake_renderer(package, movie, manifest, subtitles, *, fps, adaptive):
    assert not adaptive
    result = _report(package)
    movie.write_bytes(b"NONRENDER-TEST-ONLY")
    manifest.write_text(json.dumps(result), encoding="utf-8")
    subtitles.write_text("NONRENDER-TEST-ONLY", encoding="utf-8")
    return result


def _session(tmp_path):
    package = tmp_path / "course"
    build(package)
    source = package / "spoken_classroom.json"
    export_spoken_script(
        checked_spoken(source, adaptive=False),
        output_json=package / "lesson_script.json",
        output_md=package / "lesson_script.md",
        source_document=json.loads(source.read_text(encoding="utf-8")),
    )
    movie = tmp_path / "baseline.mp4"
    movie.write_bytes(b"NONRENDER-BASELINE")
    manifest = tmp_path / "baseline.json"
    manifest.write_text(json.dumps(_report(package)), encoding="utf-8")
    root = tmp_path / "session"
    create_session(
        package, movie, manifest, root, adaptive=False, media_check=_fake_media,
    )
    return root


def _edit_plan(source):
    doc = json.loads(source.read_text(encoding="utf-8"))
    position = len(doc["events"]) - 1
    old = doc["events"][position]["spans"][0]["parts"][0]["value"]
    return {
        "schema_version": "1.0", "model": "reviewed-test-agent",
        "requirements": [{
            "id": "r1", "instruction": "让最后归纳更简洁",
            "target": "最后归纳", "operation_ids": ["o1"],
        }],
        "operations": [{
            "id": "o1", "file": "spoken_classroom.json",
            "pointer": f"/events/{position}/spans/0/parts/0/value",
            "action": "set",
            "value": old + "另外，积分限要跟着变量同步变化。",
        }],
    }


def test_v27_edit_requires_both_mathematical_and_script_approval(tmp_path):
    root = _session(tmp_path)
    baseline = (root / "latest.mp4").read_bytes()
    initial = _state(root)["latest_source_spoken_sha256"]
    agent = lambda instruction, package, history: _edit_plan(
        package / "spoken_classroom.json"
    )

    no_math = run_edit(
        root, "修改归纳", agent, renderer=_fake_renderer,
        media_check=_fake_media,
    )
    assert no_math["status"] == "failed"
    assert "EDIT_MATH_REVIEW_REQUIRED" in no_math["error"]
    assert all(r["status"] == "failed" for r in no_math["requirements"])
    assert (root / "latest.mp4").read_bytes() == baseline

    no_script = run_edit(
        root, "修改归纳", agent, renderer=_fake_renderer,
        media_check=_fake_media, math_reviewer=lambda *args: True,
    )
    assert no_script["status"] == "failed"
    assert "EDIT_V27_SCRIPT_REVIEW_REQUIRED" in no_script["error"]
    assert (root / "latest.mp4").read_bytes() == baseline

    observed = []
    def approve_script(md, json_path):
        assert md.read_text(encoding="utf-8").startswith(
            "# 真实教师完整口播"
        )
        doc = json.loads(json_path.read_text(encoding="utf-8"))
        assert doc["source_spoken_sha256"] != initial
        observed.append(doc["source_spoken_sha256"])
        return True

    approved = run_edit(
        root, "修改归纳", agent, renderer=_fake_renderer,
        media_check=_fake_media, math_reviewer=lambda *args: True,
        script_reviewer=approve_script,
    )
    assert approved["status"] == "preview_ready"
    assert approved["revision"] == 1
    assert observed == [_state(root)["latest_source_spoken_sha256"]]
    assert all(r["status"] == "completed" for r in approved["requirements"])
    version = root / "versions" / "0001" / "package"
    assert (version / "lesson_script.md").is_file()
    source = version / "spoken_classroom.json"
    assert require_prerender_script(
        checked_spoken(source, adaptive=False), source
    )["source_spoken_sha256"] == observed[0]
    assert (root / "versions" / "0000" / "movie.mp4").read_bytes() == baseline


def test_v27_script_reviewer_rejection_keeps_previous_video(tmp_path):
    root = _session(tmp_path)
    initial = (root / "latest.mp4").read_bytes()
    result = run_edit(
        root, "更新归纳",
        lambda instruction, package, history: _edit_plan(
            package / "spoken_classroom.json"
        ),
        renderer=_fake_renderer, media_check=_fake_media,
        math_reviewer=lambda *args: True,
        script_reviewer=lambda *args: False,
    )
    assert result["status"] == "failed"
    assert "EDIT_V27_SCRIPT_REVIEW_REJECTED" in result["error"]
    assert result["revision"] == 0
    assert (root / "latest.mp4").read_bytes() == initial
    assert all(r["status"] == "failed" for r in result["requirements"])


def test_v27_voice_only_edit_bypasses_math_but_requires_script_review(tmp_path):
    root = _session(tmp_path)
    def voice_plan(*args):
        return {
            "schema_version": "1.0", "model": "test-agent",
            "requirements": [{
                "id": "r", "instruction": "只改音色", "target": "voice",
                "operation_ids": ["o"],
            }],
            "operations": [{
                "id": "o", "file": "spoken_classroom.json",
                "pointer": "/voice", "action": "set",
                "value": "zh-CN-YunxiNeural",
            }],
        }
    result = run_edit(
        root, "只改音色", voice_plan,
        renderer=_fake_renderer, media_check=_fake_media,
        script_reviewer=lambda md, json_path: True,
    )
    assert result["status"] == "preview_ready"
