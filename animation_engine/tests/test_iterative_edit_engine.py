"""V2.6.5 unit tests use MOCK renderers, never claim fake media is real TTS.

The separate integration workflow renders genuine neural speech and MathTex.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from build_spoken_triangle import export_spoken_triangle
from animation_engine.iterative_edit_ops import (
    EditEngineError, apply_json_operations, canonical_digest, safe_json_file,
)
from animation_engine.iterative_edit_engine import (
    create_session, export_history, record_feedback, run_edit,
    session_lock, _state,
)
from animation_engine.iterative_ai_adapter import make_openai_compatible_agent
from animation_engine.spoken_classroom import checked_spoken


def fake_report(package, adaptive=True):
    contract=checked_spoken(package/"spoken_classroom.json",adaptive=adaptive)
    count=sum(len(x.spans) for x in contract.events)
    return {
        "source_spoken_sha256":contract.source_sha256,
        "source_flow_sha256":contract.flow.source_sha256,
        "voice_status":"real_edge_neural_pcm_verified",
        "subtitle_status":"actual_tts_phrase_aligned",
        "math_caption_renderer":"true_manim_mathtex",
        "voiced_action_count":count,
        "source_narration_action_count":count,
        "fabricated_voice_or_subtitle_count":0,
        "audio_verification":{"sample_rate":24000,"channels":1},
    }


def mock_renderer(package, movie, manifest, subtitles, *, fps, adaptive):
    """Tests only source & state orchestration, NOT actual audio authenticity."""
    report=fake_report(package,adaptive)
    source=json.loads((package/"spoken_classroom.json").read_text(encoding="utf-8"))
    first=source["events"][0]["spans"][0]["parts"][0]["value"]
    movie.write_bytes(("TEST-ONLY-NOT-MP4:"+first).encode("utf-8"))
    manifest.write_text(json.dumps(report),encoding="utf-8")
    subtitles.write_text("MOCK-ONLY\n",encoding="utf-8")
    return report


def stub_check(path):
    assert path.is_file()


@pytest.fixture
def session(tmp_path):
    input_dir=tmp_path/"package"
    export_spoken_triangle(input_dir)
    initial=tmp_path/"original.mp4"
    initial.write_bytes(b"TEST-ONLY-NOT-REAL-VOICE")
    manifest=tmp_path/"original.json"
    manifest.write_text(json.dumps(fake_report(input_dir)),encoding="utf-8")
    root=tmp_path/"session"
    create_session(input_dir,initial,manifest,root,
                   adaptive=True,media_check=stub_check)
    return root


def proposal(changes, *, model="test-agent", instructions=None):
    reqs=[]
    ops=[]
    for i,(pointer,value) in enumerate(changes,1):
        oid=f"patch_{i}"
        ops.append({
            "id":oid,"file":"spoken_classroom.json",
            "pointer":pointer,"action":"set","value":value,
        })
        reqs.append({
            "id":f"request_{i}",
            "instruction":(
                instructions[i-1] if instructions else f"Change {i}"),
            "target":pointer,"operation_ids":[oid],
        })
    return {
        "schema_version":"1.0","model":model,
        "requirements":reqs,"operations":ops,
    }


FIRST="/events/0/spans/0/parts/0/value"
SECOND="/events/1/spans/0/parts/0/value"


def test_multi_request_one_round_then_unhappy_then_satisfied(session,tmp_path):
    text1=(
        "第一幕讲解更自然。 Second scene should explain clearly. "
        "وتأكد من عدم حذف الحسابات."
    )
    p1=proposal([
        (FIRST,"这是一道直角三角形的题，我们先辨认两条直角边，再求斜边。"),
        (SECOND,"直角位于这个顶点，两条直角边互相垂直。"),
    ],instructions=["第一幕自然讲解","Second scene should explain clearly"])
    r1=run_edit(session,text1,lambda text,src,history:p1,
                renderer=mock_renderer,media_check=stub_check)
    assert r1["status"]=="preview_ready"
    assert r1["revision"]==1
    assert len(r1["requirements"])==2
    assert (session/"latest.mp4").read_bytes().startswith(b"TEST-ONLY-NOT-MP4")
    version1=json.loads((session/"versions/0001/package/spoken_classroom.json")
                        .read_text(encoding="utf-8"))
    assert version1["events"][0]["spans"][0]["parts"][0]["value"]==p1["operations"][0]["value"]

    feedback=record_feedback(session,"这次第一幕可以，第二幕还需要继续修改。")
    assert feedback["status"]=="needs_revision"
    text2="把第二幕的解释继续改自然，保留第一幕已经确认满意的效果。"
    def second_round(text,package,history):
        assert text==text2
        assert history[0]["feedback"].startswith("这次第一幕可以")
        current=json.loads((package/"spoken_classroom.json")
                           .read_text(encoding="utf-8"))
        assert current["events"][0]["spans"][0]["parts"][0]["value"]==p1["operations"][0]["value"]
        return proposal([(SECOND,"注意这是直角顶点，两条边成直角，我们再标清斜边。")])
    r2=run_edit(session,text2,second_round,
                renderer=mock_renderer,media_check=stub_check)
    assert r2["status"]=="preview_ready" and r2["revision"]==2
    mark=record_feedback(session,"满意了，可以结束。",satisfied=True)
    assert mark["status"]=="accepted"
    assert _state(session)["satisfied"] is True

    exported=export_history(session,tmp_path/"edits.json")
    assert len(exported["rounds"])==2
    assert exported["rounds"][0]["original_instruction"]==text1
    assert exported["rounds"][1]["original_instruction"]==text2
    assert exported["rounds"][0]["feedback"].startswith("这次第一幕可以")
    assert exported["rounds"][1]["feedback"]=="满意了，可以结束。"
    assert exported["rounds"][1]["operations"][0]["before"]==p1["operations"][1]["value"]
    assert exported["rounds"][1]["operations"][0]["after"]=="注意这是直角顶点，两条边成直角，我们再标清斜边。"
    assert exported["current_satisfied"] is True
    assert not (session/"comparison.mp4").exists()


@pytest.mark.parametrize("bad,expected",[
    ("answer","SPOKEN_EXTERNAL_ANSWER_REFERENCE"),
    ("no_speech","SPOKEN_TEXT_NOT_NATURAL"),
    ("fake_voice","SPOKEN_VOICE_NOT_APPROVED"),
    ("unsupported_math","SPOKEN_MATH_NOT_READ"),
])
def test_fail_closed_preserves_last_movie_and_records_attempt(session,bad,expected):
    old=(session/"latest.mp4").read_bytes()
    if bad=="answer":
        patch=proposal([(FIRST,"由答案可知，我们下一步计算周长。")])
    elif bad=="no_speech":
        patch=proposal([(FIRST,"  ")])
    elif bad=="fake_voice":
        patch=proposal([("/voice","zh-CN-FakeNeural")])
    else:
        mathpath="/events/0/spans/2/parts/1/latex"
        patch=proposal([(mathpath,"x=42")])
    result=run_edit(session,"这里重新做一下",lambda *args:patch,
                    renderer=mock_renderer,media_check=stub_check)
    assert result["status"]=="failed"
    assert expected in result["error"]
    assert result["revision"]==0
    assert (session/"latest.mp4").read_bytes()==old
    exported=export_history(session,session/"history.json")
    assert exported["rounds"][0]["status"]=="failed"
    assert exported["rounds"][0]["original_instruction"]=="这里重新做一下"


def test_failed_renderer_does_not_replace_latest_and_can_retry(session):
    first=run_edit(session,"第一次语音修改",lambda *a:proposal([(FIRST,"先看题目。")]),
                   renderer=mock_renderer,media_check=stub_check)
    assert first["revision"]==1
    old=(session/"latest.mp4").read_bytes()
    def crashed_renderer(*a,**kw):
        raise RuntimeError("TTS service unavailable")
    fail=run_edit(session,"第二轮语音调整",lambda *a:proposal([(FIRST,"再看题目。")]),
                  renderer=crashed_renderer,media_check=stub_check)
    assert fail["status"]=="failed"
    assert "TTS service unavailable" in fail["error"]
    assert fail["revision"]==1 and (session/"latest.mp4").read_bytes()==old
    good=run_edit(session,"再改一次",lambda *a:proposal([(FIRST,"重新分析题目。")]),
                  renderer=mock_renderer,media_check=stub_check)
    assert good["status"]=="preview_ready" and good["revision"]==2
    assert _state(session)["attempt"]==3


def test_plan_cannot_silently_omit_requirement(session):
    p=proposal([(FIRST,"换一种说法。")])
    p["requirements"].append({
        "id":"req-extra","instruction":"另一个要求","target":"e_final",
        "operation_ids":["operation_missed"],
    })
    result=run_edit(session,"第一条修改，第二条修改",
                    lambda *a:p,renderer=mock_renderer,media_check=stub_check)
    assert result["status"]=="failed"
    assert "EDIT_REQUIREMENT_OPERATION_COVERAGE" in result["error"]


def test_arbitrary_multilingual_input_retained_exactly(session):
    source="この説明を直してください。 Keep all formulas. Исправь паузу. مرحبا."
    result=run_edit(session,source,lambda *a:proposal([
        (FIRST,"题目要求求直角三角形的斜边和周长。")
    ]),renderer=mock_renderer,media_check=stub_check)
    assert result["status"]=="preview_ready"
    assert _state(session)["history"][0]["original_instruction"]==source


def test_unsafe_paths_and_plan_fields_rejected(session,tmp_path):
    package=session/"versions/0000/package"
    for attack in ("../secret.json","/etc/passwd","x/../../y.json",
                   "spoken_classroom.py"):
        with pytest.raises(EditEngineError,match="EDIT_UNSAFE_TARGET_PATH"):
            safe_json_file(package,attack)
    p=proposal([(FIRST,"新的课堂讲法。")])
    p["operations"][0]["file"]="../private.json"
    with pytest.raises(EditEngineError,match="EDIT_UNSAFE_TARGET_PATH"):
        apply_json_operations(package,p)
    p=proposal([(FIRST,"自然讲解。")])
    p["operations"][0]["pointer"]="/events/9999/foo"
    with pytest.raises(EditEngineError,match="EDIT_POINTER_NOT_FOUND"):
        apply_json_operations(package,p)
    p=proposal([(FIRST,"新的自然讲解。")])
    p["operations"].append(p["operations"][0])
    with pytest.raises(EditEngineError,match="EDIT_DUPLICATE_OPERATION"):
        apply_json_operations(package,p)


def test_locked_session_fails_immediately_and_no_journal_mutation(session):
    with session_lock(session):
        with pytest.raises(EditEngineError,match="EDIT_SESSION_LOCKED"):
            run_edit(session,"用户提出一个修改",
                lambda *a:proposal([(FIRST,"新的讲解。")]),
                renderer=mock_renderer,media_check=stub_check)
    assert _state(session)["attempt"]==0


def test_export_only_json(session,tmp_path):
    with pytest.raises(EditEngineError,match="EDIT_ONLY_JSON_EXPORT"):
        export_history(session,tmp_path/"history.csv")


def test_real_model_adapter_requires_explicit_configuration_and_api_key(tmp_path,monkeypatch):
    config=tmp_path/"openai.json"
    config.write_text(json.dumps({
        "kind":"openai_compatible", "model":"some-model",
        "endpoint":"https://example.com/v1/chat/completions",
        "key_environment":"PRIVATE_EDIT_KEY",
    }))
    agent=make_openai_compatible_agent(config)
    monkeypatch.delenv("PRIVATE_EDIT_KEY",raising=False)
    with pytest.raises(EditEngineError,match="EDIT_AI_API_KEY_MISSING"):
        agent("修改任何语言的句子",tmp_path,[])
    config.write_text(json.dumps({
        "kind":"openai_compatible","model":"some-model",
        "endpoint":"http://remote.example.com/v1/chat/completions",
        "key_environment":"PRIVATE_EDIT_KEY",
    }))
    with pytest.raises(EditEngineError,match="EDIT_AI_ENDPOINT_MUST_BE_HTTPS"):
        make_openai_compatible_agent(config)
