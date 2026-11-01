"""V2.6.4 no-silent-teaching and source-linked narration acceptance."""
import copy
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from build_spoken_triangle import export_spoken_triangle
from animation_engine.spoken_classroom import checked_spoken, plan_spoken
from animation_engine.longboard_plan import LongboardError


@pytest.fixture
def example(tmp_path):
    root=tmp_path/"spoken"
    export_spoken_triangle(root)
    return root


def get(root):
    return json.loads((root/"spoken_classroom.json").read_text(encoding="utf-8"))


def put(root,payload):
    (root/"spoken_classroom.json").write_text(
        json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )


def test_every_real_math_note_and_diagram_is_spoken(example):
    c=checked_spoken(example/"spoken_classroom.json",adaptive=True)
    p=plan_spoken(example/"spoken_classroom.json",adaptive=True)
    assert p["source_spoken_sha256"]==c.source_sha256
    assert p["event_count"]==11
    assert p["action_count"]==sum(len(e.spans) for e in c.events)
    assert p["action_count"]>=p["event_count"]
    assert p["math_writes_all_voiced"]
    assert all(s.tts_text and s.parts for event in c.events for s in event.spans)
    assert sum(s.kind=="math" for ev in c.events for s in ev.spans)==11
    assert any(s.kind=="diagram" for ev in c.events for s in ev.spans)
    assert any(s.kind=="note" for ev in c.events for s in ev.spans)
    assert all(
        s.math_latex in [part["latex"] for part in s.parts if part["kind"]=="math"]
        for event in c.events for s in event.spans if s.kind=="math"
    )


@pytest.mark.parametrize("variant,error",[
    ("not_reviewed","SPOKEN_INVALID_MANIFEST"),
    ("unknown_mode","SPOKEN_INVALID_MANIFEST"),
    ("fake_source","SPOKEN_SOURCE_CHANGED"),
    ("unknown_voice","SPOKEN_VOICE_NOT_APPROVED"),
    ("missing_event","SPOKEN_EVENT_COVERAGE"),
    ("wrong_event_order","SPOKEN_EVENT_ORDER"),
    ("no_cue_coverage","SPOKEN_TEACHING_CUE_UNCOVERED"),
    ("question_silent","SPOKEN_QUESTION_NOT_READ"),
    ("question_wrong_source","SPOKEN_QUESTION_SOURCE_MUTATED"),
    ("missing_span","SPOKEN_ACTION_COVERAGE"),
    ("swapped_math_object","SPOKEN_ACTION_ORDER"),
    ("silenced_math","SPOKEN_SILENT_ACTION"),
    ("omitted_math","SPOKEN_MATH_NOT_READ"),
    ("changed_latex","SPOKEN_MATH_NOT_READ"),
    ("missing_pronunciation","SPOKEN_MATH_PRONUNCIATION_MISSING"),
    ("future_math_in_diagram","SPOKEN_UNSOURCED_CAPTION_MATH"),
    ("no_explanation","SPOKEN_NO_TEACHING_EXPLANATION"),
    ("latex_in_chinese","SPOKEN_TEXT_NOT_NATURAL"),
    ("wrong_span_fields","SPOKEN_SPAN_FIELDS"),
    ("foreign_answer","SPOKEN_EXTERNAL_ANSWER_REFERENCE"),
    ("answers_reference","SPOKEN_EXTERNAL_ANSWER_REFERENCE"),
    ("derived_from_answer","SPOKEN_EXTERNAL_ANSWER_REFERENCE"),
    ("teacher_notes_silent","SPOKEN_ACTION_COVERAGE"),
])
def test_reject_missing_narration_and_answer_source_language(example,variant,error):
    data=get(example)
    ev=data["events"]
    first=ev[0]
    math=next(s for e in ev for s in e["spans"] if s["kind"]=="math")
    if variant=="not_reviewed": data["teacher_reviewed"]=False
    elif variant=="unknown_mode": data["mode"]="silence_dub"
    elif variant=="fake_source": data["source_flow_sha256"]="0"*64
    elif variant=="unknown_voice": data["voice"]="unknown"
    elif variant=="missing_event": ev.pop()
    elif variant=="wrong_event_order": first["event_id"]="e_wrong"
    elif variant=="no_cue_coverage": first["pedagogical_cue_covered"]=False
    elif variant=="question_silent": first["question_read_aloud"]=False
    elif variant=="question_wrong_source": first["question_source_sha256"]="0"*64
    elif variant=="missing_span": first["spans"].pop()
    elif variant=="swapped_math_object": math["object_id"]="m_unknown"
    elif variant=="silenced_math": math["parts"]=[]
    elif variant=="omitted_math":
        math["parts"]= [{"kind":"text","value":"这个式子可以继续计算。"}]
    elif variant=="changed_latex":
        next(x for x in math["parts"] if x["kind"]=="math")["latex"]="x=42"
    elif variant=="missing_pronunciation":
        next(x for x in math["parts"] if x["kind"]=="math")["reading"]=""
    elif variant=="future_math_in_diagram":
        non=next(s for e in ev for s in e["spans"] if s["kind"]=="diagram")
        non["parts"].append({"kind":"math","latex":"x=42","reading":"x等于四十二"})
    elif variant=="no_explanation":
        math["parts"]=[x for x in math["parts"] if x["kind"]=="math"]
    elif variant=="latex_in_chinese":
        math["parts"][0]["value"]="根据\\frac{1}{2}我们继续。"
    elif variant=="wrong_span_fields":
        math["unreviewed_extra"]=1
    elif variant=="foreign_answer":
        math["parts"][0]["value"]="按照答案，我们可以这样列式。"
    elif variant=="answers_reference":
        math["parts"][0]["value"]="由参考答案可知，这一步的结果是这样的。"
    elif variant=="derived_from_answer":
        math["parts"][0]["value"]="由答案可知，这一步的结果是这样的。"
    elif variant=="teacher_notes_silent":
        first["spans"]=[x for x in first["spans"] if x["kind"]!="note"]
    put(example,data)
    with pytest.raises(LongboardError,match=error):
        checked_spoken(example/"spoken_classroom.json",adaptive=True)


@pytest.mark.parametrize("voice",["zh-CN-YunxiNeural","zh-CN-XiaoxiaoNeural"])
def test_both_user_approved_voices_keep_the_same_math_and_narration(example, voice):
    data=get(example)
    data["voice"]=voice
    data["speech_rate"]="+1%"
    put(example,data)
    contract=checked_spoken(example/"spoken_classroom.json",adaptive=True)
    plan=plan_spoken(example/"spoken_classroom.json",adaptive=True)
    assert contract.voice==plan["voice"]==voice
    assert contract.speech_rate==plan["speech_rate"]=="+1%"
    assert plan["math_writes_all_voiced"] and plan["action_count"]==18


def test_legacy_missing_rate_defaults_to_approved_five_percent_faster(example):
    data=get(example)
    data.pop("speech_rate",None)
    put(example,data)
    assert checked_spoken(example/"spoken_classroom.json",adaptive=True).speech_rate=="+1%"


@pytest.mark.parametrize("rate",["-4%","+1%","+5%","-30%","+30%"])
def test_reviewed_speech_rate_is_configurable(example,rate):
    data=get(example)
    data["speech_rate"]=rate
    put(example,data)
    assert checked_spoken(example/"spoken_classroom.json",adaptive=True).speech_rate==rate


@pytest.mark.parametrize("rate",["1%","101%","fast","+31%","-31%","",None,0,True])
def test_unapproved_or_malformed_speech_rates_fail_closed(example,rate):
    data=get(example)
    data["speech_rate"]=rate
    put(example,data)
    with pytest.raises(LongboardError,match="SPOKEN_RATE_NOT_APPROVED"):
        checked_spoken(example/"spoken_classroom.json",adaptive=True)
