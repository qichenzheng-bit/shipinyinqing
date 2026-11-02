"""Fresh final lesson: offline math correctness and V2.7 provenance smoke.

No model credentials, model hub, or speech service is needed for this test.
A rendered MP4 is separately verified by the on-demand media acceptance job.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sympy import Rational, cos, limit, series, sin, symbols

from animation_engine.spoken_classroom import checked_spoken
from animation_engine.spoken_audio import split_natural_phrases
from animation_engine.unified_classroom_flow import checked_flow
from animation_engine.v27_teacher_contract import export_spoken_script
from animation_engine.video_settings import DEFAULT_VIDEO_FPS

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from build_final_fresh_trig_limit import build  # noqa: E402


def test_fresh_trigonometric_question_independently_verified():
    x = symbols("x", real=True)
    numerator = sin(x) - x * cos(x)
    assert limit(numerator / x**3, x, 0) == Rational(1, 3)
    # The numerator has no surviving first- or second-order term.
    assert series(numerator, x, 0, 5).removeO().expand() == x**3 / 3
    assert DEFAULT_VIDEO_FPS == 60


def test_fresh_offline_package_and_script_are_source_exact(tmp_path):
    output = tmp_path / "fresh_trig"
    spoken = build(output)
    assert len(spoken["events"]) == 12
    assert spoken["voice"] == "zh-CN-XiaoxiaoNeural"
    assert spoken["speech_rate"] == "+5%"
    flow = checked_flow(output / "unified_flow.json")
    checked = checked_spoken(output / "spoken_classroom.json", adaptive=False)
    # Real TTS pipeline refuses clauses that cannot be split naturally.
    for event in spoken["events"]:
        for span in event["spans"]:
            for part in span["parts"]:
                if part["kind"] == "text":
                    phrases = split_natural_phrases(part["value"])
                    assert "".join(phrases) == part["value"]
    assert len(flow.stages) == 1
    assert checked.flow.lesson_id == "final_fresh_sine_cosine_limit"

    script_md = output / "lesson_script.md"
    script_json = output / "lesson_script.json"
    exported = export_spoken_script(
        checked, output_json=script_json, output_md=script_md,
        source_document=spoken, source_path=output / "spoken_classroom.json",
    )
    assert exported["acceptance"]["contract_version"] == "2.7"
    assert exported["events"][0]["phase"] == "observe"
    assert exported["events"][-1]["phase"] == "summary"
    text = script_md.read_text(encoding="utf-8")
    assert "我们来读一下这道题" not in text
    assert "括号里的每一项都需要变号" in text
    doc = json.loads(script_json.read_text(encoding="utf-8"))
    assert doc == exported

    summary = next(item for item in spoken["events"] if item["event_id"] == "e_summary")
    summary_speech = " ".join(
        part["value"] for span in summary["spans"] for part in span["parts"]
        if part["kind"] == "text"
    )
    assert "三阶展开" in summary_speech
    assert "括号" in summary_speech
    assert "L 等于三分之一" not in summary_speech

    # No AI provider call or premature video claim is hidden in the offline test.
    assert not list(output.rglob("*.mp4"))
    assert not (output / "lesson_script_approval.json").exists()
