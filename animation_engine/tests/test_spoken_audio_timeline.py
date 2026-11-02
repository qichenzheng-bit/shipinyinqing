"""Deterministic sample/frame/subtitle boundaries; no fake TTS success claims."""
from __future__ import annotations

import wave
import pytest

from animation_engine.spoken_audio import (
    SAMPLE_RATE,VoiceChunk,VoicedSpan,assemble_source_pcm,
    build_render_schedules,split_natural_phrases,
    compact_tts_boundary_silence,
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


def test_true_caption_band_codec_preserves_silence_and_segment_count(tmp_path):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg CLI required")
    from PIL import Image, ImageDraw
    from animation_engine.spoken_movie import _encode_caption_band
    png=tmp_path/"math.png"
    img=Image.new("RGBA",(1280,88),(0,0,0,0))
    ImageDraw.Draw(img).rectangle((100,20,300,65),fill=(8,20,40,255))
    img.save(png)
    payload=[{
        "kind":"math","display":r"BC=10",
        "start_frame":10,"end_frame":30,
    }]
    result=tmp_path/"caption_band.mkv"
    _encode_caption_band(
        payload,{("math",r"BC=10"):png},
        result,fps=30,frames=45,
    )
    frames=subprocess.check_output([
        "ffprobe","-v","error","-select_streams","v:0",
        "-count_frames","-show_entries","stream=nb_read_frames",
        "-of","default=noprint_wrappers=1:nokey=1",str(result)
    ]).decode().strip()
    assert int(frames)==45
    middle=tmp_path/"middle.png"
    subprocess.run([
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-ss","0.5","-i",str(result),"-frames:v","1",
        "-pix_fmt","rgba",str(middle)
    ],check=True)
    observed=Image.open(middle).convert("RGBA")
    assert observed.size==(1280,88)
    assert observed.getpixel((110,35))[3]>=200
    with pytest.raises(LongboardError,match="SPOKEN_CAPTION_FRAME_OVERLAP"):
        _encode_caption_band(
            [*payload,{**payload[0],"start_frame":29,"end_frame":40}],
            {("math",r"BC=10"):png},
            tmp_path/"overlap.mkv",fps=30,frames=45
        )


def test_no_math_or_text_phrase_is_arbitrarily_cut_midexpression():
    text="因此先完成变量替换然后根据新上下限积分"
    fragments=split_natural_phrases(text,limit=16)
    assert "".join(fragments)==text
    assert len(fragments)>=2
    with pytest.raises(LongboardError,match="VOICE_UNSAFE_LONG_CLAUSE"):
        split_natural_phrases("单个连续数学符号无法安全按照固定字符数拆断",limit=8)


def test_long_caption_relation_break_preserves_latex_braces():
    from animation_engine.spoken_captions import _safe_math_caption_break
    assert _safe_math_caption_break(r"I=\int_0^1 e^u\,du")==(r"I=",r"\int_0^1 e^u\,du")
    assert _safe_math_caption_break(r"\frac{1+2}{x^2}") is None

def test_connective_phrase_stays_with_following_clause_without_changing_words():
    approved="这样，这道题就算出来了。然后，我们再来看归纳总结。"
    pieces=split_natural_phrases(approved)
    assert "".join(pieces)==approved
    assert pieces[0]=="这样，这道题就算出来了。"
    assert "这样，" not in pieces
    assert "然后，" not in pieces
    # Real mathematical expressions are never cut merely to reach a quota.
    assert split_natural_phrases("x 的三次方加上 y 的三次方。")==[
        "x 的三次方加上 y 的三次方。"
    ]


def test_pcm_boundary_compaction_preserves_actual_voice_and_middle_pause():
    from array import array
    # Real signed 16-bit mono samples; no TTS or video/render dependencies.
    sr=24000
    silence=lambda sec: array("h",[0]*round(sr*sec))
    voice=lambda sec: array("h",[2000]*round(sr*sec))
    original=(silence(.85)+voice(.65)+silence(.72)+voice(.75)+silence(.96))
    result=compact_tts_boundary_silence(original.tobytes(),sample_rate=sr)
    samples=array("h");samples.frombytes(result)
    assert len(samples)<len(original)-sr
    assert samples.count(2000)==round(sr*(.65+.75))
    # Deliberate *intra*-sentence pause is kept intact.
    assert (samples.count(0)-round(sr*.72))<round(sr*.38)
    assert samples[:int(sr*.1)]==array("h",[0]*int(sr*.1))
    assert samples[-int(sr*.1):]==array("h",[0]*int(sr*.1))


def test_pcm_compaction_avoids_clip_damage_when_quiet_or_short():
    from array import array
    sr=24000
    short=array("h",[0]*4000+[1500]*5000+[0]*3500).tobytes()
    assert compact_tts_boundary_silence(short)==short
    all_silence=array("h",[0]*sr*2).tobytes()
    assert compact_tts_boundary_silence(all_silence)==all_silence
    with pytest.raises(LongboardError,match="VOICE_INVALID_PCM_FOR_SILENCE_CHECK"):
        compact_tts_boundary_silence(bytes([0]))
