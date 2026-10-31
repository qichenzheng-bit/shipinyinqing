"""Deterministic sample/frame/subtitle boundaries; no fake TTS success claims."""
from __future__ import annotations

import wave
import pytest

from animation_engine.spoken_audio import (
    SAMPLE_RATE,VoiceChunk,VoicedSpan,assemble_source_pcm,
    build_render_schedules,split_natural_phrases,
)
from animation_engine.spoken_captions import captions_srt
from animation_engine.longboard_plan import LongboardError


def sample_fixture():
    pcm=(b"\x01\x00")*4800
    chunk=VoiceChunk(
        "math",r"BC=10","B C 等于十。",pcm,4800,8,
    )
    span=VoicedSpan("math","m_hypotenuse",(chunk,),8,0)
    return {
        "calculate_hypotenuse":{
            "e_hypotenuse":(span,)
        }
    }


def fake_video():
    return {
        "actual_video_frames":61,
        "stage_render_reports":[
            {"stage_id":"calculate_hypotenuse","start_frame":0}
        ],
        "event_timing":[{
            "stage_id":"calculate_hypotenuse",
            "event_id":"e_hypotenuse",
            "action_timing":[{
                "kind":"math","object_id":"m_hypotenuse",
                "start_preview_second":10/30,
                "end_preview_second":18/30,
            }],
        }],
    }


def test_short_phrases_do_not_omit_or_reorder_any_spoken_words():
    text="先观察题目，找到直角边。然后计算斜边，最后得到周长。"
    result=split_natural_phrases(text,limit=23)
    assert "".join(result)==text
    assert all(0<len(x)<=23 for x in result)
    assert len(result)==4


def test_action_schedule_has_formula_start_offset():
    sch=build_render_schedules(sample_fixture(),fps=30)
    s=sch["calculate_hypotenuse"]["e_hypotenuse"][0]
    assert s["kind"]=="math" and s["object_id"]=="m_hypotenuse"
    assert s["duration"]==8/30
    assert s["math_start_delay"]==0


def test_real_action_offsets_are_used_for_pcm_and_srt(tmp_path):
    dest=tmp_path/"aligned.wav"
    cues=assemble_source_pcm(sample_fixture(),fake_video(),dest,fps=30)
    assert len(cues)==1
    assert cues[0]["start_frame"]==10
    assert cues[0]["end_frame"]==16
    assert cues[0]["kind"]=="math"
    assert cues[0]["display"]==r"BC=10"
    with wave.open(str(dest),"rb") as w:
        assert w.getframerate()==SAMPLE_RATE
        assert w.getnchannels()==1
        data=w.readframes(w.getnframes())
    assert not any(data[:2*int(10*SAMPLE_RATE/30)])
    assert data[2*int(10*SAMPLE_RATE/30):][:10]==b"\x01\x00"*5
    assert not any(data[2*int(16*SAMPLE_RATE/30):])
    srt=captions_srt(cues,fps=30)
    assert r"\(BC=10\)" in srt
    assert "00:00:00,333 --> 00:00:00,533" in srt


def test_tampered_action_duration_rejected(tmp_path):
    manifest=fake_video()
    manifest["event_timing"][0]["action_timing"][0]["end_preview_second"]=1.2
    with pytest.raises(LongboardError,match="VOICE_ACTUAL_VISUAL_DESYNC"):
        assemble_source_pcm(
            sample_fixture(),manifest,tmp_path/"invalid.wav",fps=30
        )


def test_audio_timeline_rejects_duplicate_same_math_action(tmp_path):
    source=fake_video()
    source["event_timing"].append(source["event_timing"][0].copy())
    with pytest.raises(LongboardError,match="VOICE_DUPLICATE_VIDEO_ACTION"):
        assemble_source_pcm(
            sample_fixture(),source,tmp_path/"duplicated.wav",fps=30
        )
