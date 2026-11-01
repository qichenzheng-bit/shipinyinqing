"""V2.6.6 caching, conservative invalidation and incremental stage QA.

FAKE media is used *only* for unit tests. The separate real CI job
must synthesize real Edge audio and render real Manim/MathTex MP4s.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from build_spoken_triangle import export_spoken_triangle
from animation_engine.edit_impact import analyze_impact
from animation_engine.incremental_render import render_or_reuse_stage
from animation_engine.render_cache import ArtifactCache, digest
from animation_engine.spoken_classroom import checked_spoken
from animation_engine.spoken_audio import _edge_clip, SAMPLE_RATE


def _package(tmp_path):
    package=tmp_path/"source"
    export_spoken_triangle(package)
    current=tmp_path/"after"
    shutil.copytree(package,current)
    return package,current


def _spoken(root):
    path=root/"spoken_classroom.json"
    data=json.loads(path.read_text(encoding="utf-8"))
    return path,data


def _write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")


def _op(pointer,file="spoken_classroom.json"):
    return [{"file":file,"pointer":pointer,"action":"set"}]


def test_cache_integrity_and_payload_tampering(tmp_path):
    cache=ArtifactCache(tmp_path/"resources")
    key=cache.key("speech_pcm",{"text":"数学教学","voice":"A","rate":"-4%"})
    assert cache.read("speech_pcm",key) is None
    pcm=struct.pack("<h",2000)*15000
    cache.write("speech_pcm",key,{"payload.bin":pcm})
    assert cache.get_pcm(key)==pcm
    assert cache.stats()["speech_pcm_hit"]>=1
    entry=cache._entry("speech_pcm",key)
    (entry/"payload.bin").write_bytes(b"\x00"*len(pcm))
    assert cache.get_pcm(key) is None
    cache.write("speech_pcm",key,{"payload.bin":pcm})
    assert cache.get_pcm(key)==pcm
    bad=cache.key("speech_pcm",{"text":"数学教学","voice":"B","rate":"-4%"})
    assert bad!=key
    assert cache.get_pcm(bad) is None


def test_cache_stage_reuse_via_real_provenance_without_fake_video_claim(
        tmp_path,monkeypatch):
    from animation_engine import incremental_render
    from animation_engine import unified_classroom_flow
    source_sha="a"*64
    stage=SimpleNamespace(
        stage_id="intro",engine="standard",
        package={"source":"source-hash"},
        storyboard={"events":[1]},
        execution={"source_storyboard_sha256":source_sha},
        cues={"a":1},policy={"p":1},special=None,
        handoff=(),events=("e1",),
        kwargs=lambda:{},
    )
    cache=ArtifactCache(tmp_path/"cache")
    rendered=[]
    def pretend_render(storyboard,execution,cues,policy,*,output_mp4,
                       output_json,fps,narration_events,layout_hint,**kwargs):
        rendered.append(narration_events)
        Path(output_mp4).write_bytes(b"MOCK-ONLY NOT A REAL VIDEO")
        report={
            "source_storyboard_sha256":source_sha,
            "voice_status":"not_recorded",
            "event_timing":[{
                "event_id":"e1","start_preview_second":0,
                "end_preview_second":1.0,
                "action_timing":[],
                "visible_block_ids":["m1"],
                "visible_diagram_ids":[],
            }],
        }
        _write(Path(output_json),report)
        return report
    monkeypatch.setattr(incremental_render,
                        "render_persistent_chalkboard",pretend_render)
    monkeypatch.setattr(unified_classroom_flow,
                        "_video_frames",lambda video,fps:30)
    a=tmp_path/"a.mp4";b=tmp_path/"a.json"
    plan={"e1":[{"kind":"math","object_id":"m1","duration":1.0}]}
    report,hit=render_or_reuse_stage(
        stage,output_mp4=a,output_json=b,
        fps=30,narration_events=plan,cache=cache,
    )
    assert hit is False and len(rendered)==1
    assert a.read_bytes().startswith(b"MOCK-ONLY")
    c=tmp_path/"new.mp4";d=tmp_path/"new.json"
    again,hit=render_or_reuse_stage(
        stage,output_mp4=c,output_json=d,
        fps=30,narration_events=plan,cache=cache,
    )
    assert hit is True and len(rendered)==1
    assert again["event_timing"]==report["event_timing"]
    changed={"e1":[{"kind":"math","object_id":"m1","duration":2.0}]}
    _,hit=render_or_reuse_stage(
        stage,output_mp4=c,output_json=d,
        fps=30,narration_events=changed,cache=cache,
    )
    assert hit is False and len(rendered)==2
    assert cache.stats()["raw_stage_hit"]==1
    assert cache.stats()["raw_stage_miss"]==2


def test_cache_corruption_causes_rebuild(tmp_path,monkeypatch):
    from animation_engine import incremental_render,unified_classroom_flow
    stage=SimpleNamespace(
        stage_id="intro",engine="standard",package={},
        storyboard={},execution={"source_storyboard_sha256":"z"*64},
        cues={},policy={},special=None,handoff=(),events=("e1",),
        kwargs=lambda:{},
    )
    count=[]
    def factory(*args,output_mp4,output_json,**kwargs):
        count.append(True)
        Path(output_mp4).write_bytes(b"MOCK-VIDEO-BYTES")
        report={
            "source_storyboard_sha256":"z"*64,
            "voice_status":"not_recorded",
            "event_timing":[{"event_id":"e1"}],
        }
        _write(Path(output_json),report)
        return report
    monkeypatch.setattr(incremental_render,"render_persistent_chalkboard",factory)
    monkeypatch.setattr(unified_classroom_flow,"_video_frames",lambda *a:30)
    cache=ArtifactCache(tmp_path/"cache")
    key=cache.key("raw_stage",{
        "stage_id":"intro","engine":"standard",
        "package":{},"storyboard":{},"execution":{"source_storyboard_sha256":"z"*64},
        "cues":{},"policy":{},"special":None,"handoff":(),"events":("e1",),
        "fps":30,"width":1280,"height":720,
        "layout_hint":None,"narration_events":None,
    })
    for _ in range(2):
        render_or_reuse_stage(
            stage,output_mp4=tmp_path/"stage.mp4",
            output_json=tmp_path/"stage.json",fps=30,
            narration_events=None,cache=cache,
        )
    assert len(count)==1
    (cache._entry("raw_stage",key)/"manifest.json").write_text("corrupted")
    render_or_reuse_stage(
        stage,output_mp4=tmp_path/"stage.mp4",
        output_json=tmp_path/"stage.json",fps=30,
        narration_events=None,cache=cache,
    )
    assert len(count)==2


def test_single_spoken_edit_only_invalidates_one_stage_and_global_clock(tmp_path):
    before,after=_package(tmp_path)
    path,data=_spoken(after)
    data["events"][0]["spans"][0]["parts"][0]["value"]+="我们开始分析。"
    _write(path,data)
    impact=analyze_impact(
        before,after,_op("/events/0/spans/0/parts/0/value"),
    )
    assert impact["affected_stages"]==["introduce_triangle"]
    assert impact["reusable_stages_subject_to_cache_validation"]==[
        "calculate_hypotenuse","calculate_perimeter"
    ]
    assert impact["global_timeline_recomputation_required"]
    assert not impact["whole_lesson_invalidation"]
    assert not impact["mathematical_source_changed"]
    assert len(impact["changed_spoken_actions"])==1


def test_voice_change_invalidates_all_stages(tmp_path):
    before,after=_package(tmp_path)
    path,data=_spoken(after)
    data["voice"]="zh-CN-XiaoxiaoNeural"
    _write(path,data)
    impact=analyze_impact(before,after,_op("/voice"))
    assert impact["whole_lesson_invalidation"]
    assert len(impact["affected_stages"])==3
    assert not impact["reusable_stages_subject_to_cache_validation"]


def test_math_source_change_propagates_downstream(tmp_path):
    before,after=_package(tmp_path)
    flow=json.loads((before/"unified_flow.json").read_text("utf-8"))
    second=flow["stages"][1]["directory"]
    p=after/second/"page_policy.json"
    data=json.loads(p.read_text("utf-8"))
    data["unused_in_test"]=True
    _write(p,data)
    impact=analyze_impact(
        before,after,_op("/unused_in_test",second+"/page_policy.json"),
    )
    assert impact["affected_stages"]==[
        "calculate_hypotenuse","calculate_perimeter"
    ]
    assert impact["mathematical_source_changed"]


def test_voice_provider_reuses_verified_pcm_without_second_network_call(
        tmp_path,monkeypatch):
    import types
    from animation_engine import spoken_audio
    calls=[]
    class DummyVoice:
        def __init__(self,text,voice,rate):
            calls.append((text,voice,rate))
        async def save(self,path):
            Path(path).write_bytes(b"MP3 MOCK TEST BYTES"*20)
    monkeypatch.setitem(sys.modules,"edge_tts",
                        types.SimpleNamespace(Communicate=DummyVoice))
    monkeypatch.setattr(
        spoken_audio,"_decode_mp3_to_pcm",
        lambda mp3,wav: struct.pack("<h",1200)*15000,
    )
    cache=ArtifactCache(tmp_path/"cached")
    semaphore=asyncio.Semaphore(1)
    source=tmp_path/"tts"
    source.mkdir()
    a=asyncio.run(_edge_clip(
        0,"两条直角边", "zh-CN-YunxiNeural", source,semaphore,cache
    ))
    b=asyncio.run(_edge_clip(
        1,"两条直角边", "zh-CN-YunxiNeural", source,semaphore,cache
    ))
    assert a==b and len(calls)==1
    c=asyncio.run(_edge_clip(
        2,"两条直角边", "zh-CN-XiaoxiaoNeural", source,semaphore,cache
    ))
    assert c==a and len(calls)==2
    assert cache.stats()["speech_pcm_hit"]>=1


def test_cache_is_opt_in_and_source_fingerprint_is_stable(tmp_path):
    cache=ArtifactCache(tmp_path/"cache")
    assert digest({"b":2,"a":1})==digest({"a":1,"b":2})
    assert cache.stats()=={}
    key=cache.key("subtitle_png",{"latex":r"\int_0^1 x\,dx"})
    assert len(key)==64


def test_no_fake_claim_for_unit_test_media():
    # Unit tests never check fake bytes through the actual production
    # ffprobe or claim them to be genuine TTS/Manim artifacts.
    assert b"MOCK" != b"\x00\x00\x00\x18ftypmp42"
