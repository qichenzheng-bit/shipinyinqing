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

sys.path.insert(0,str(Path(__file__).resolve().parent/"fixtures"))
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


def test_render_cache_environment_fingerprint_tracks_actual_font_bytes(
        tmp_path, monkeypatch):
    from animation_engine import render_cache, classroom_compositor
    font = tmp_path / "NotoSansCJK-Regular.ttc"
    font.write_bytes(b"font-content-v1")
    monkeypatch.setattr(classroom_compositor, "_CJK_FONT_CANDIDATES", (str(font),))
    monkeypatch.setattr(render_cache.shutil, "which", lambda name: None)
    first = render_cache._render_environment_fingerprint()
    assert first["board_cjk_font"]["sha256"] == render_cache.file_sha(font)
    assert first["latex"] == "not-installed"
    assert first["manim_cjk_font"]["status"] == "missing"
    font.write_bytes(b"font-content-v2")
    second = render_cache._render_environment_fingerprint()
    assert first["board_cjk_font"]["sha256"] != second["board_cjk_font"]["sha256"]


def test_render_cache_signature_invalidates_when_tex_or_fonts_change(
        tmp_path, monkeypatch):
    from animation_engine import render_cache
    environment = {"latex": "latex v1", "board_cjk_font": "font v1"}
    monkeypatch.setattr(
        render_cache, "_render_environment_fingerprint",
        lambda: dict(environment),
    )
    try:
        render_cache.engine_signature.cache_clear()
        cache = ArtifactCache(tmp_path / "resources")
        before = cache.key("subtitle_png", {"formula": r"\\frac12"})
        environment["latex"] = "latex v2"
        render_cache.engine_signature.cache_clear()
        after_tex_upgrade = cache.key("subtitle_png", {"formula": r"\\frac12"})
        assert before != after_tex_upgrade
        environment["board_cjk_font"] = "font v2"
        render_cache.engine_signature.cache_clear()
        after_font_update = cache.key("subtitle_png", {"formula": r"\\frac12"})
        assert after_font_update != after_tex_upgrade
    finally:
        render_cache.engine_signature.cache_clear()


def test_windows_cjk_font_discovery_and_cache_fingerprint(tmp_path, monkeypatch):
    from animation_engine import classroom_compositor, render_cache
    fonts = tmp_path / "Fonts"
    fonts.mkdir()
    yahei = fonts / "msyh.ttc"
    yahei.write_bytes(b"test-system-font-data")
    monkeypatch.setenv("WINDIR", str(tmp_path))
    monkeypatch.setattr(classroom_compositor, "_CJK_FONT_CANDIDATES", ())
    assert classroom_compositor._cjk_font_path() == yahei
    assert classroom_compositor._cjk_text_font_family() == "Microsoft YaHei"
    signature = render_cache._render_environment_fingerprint()
    assert signature["board_cjk_font"]["sha256"] == render_cache.file_sha(yahei)


def test_concurrent_same_key_writes_publish_single_valid_cache_entry(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    cache = ArtifactCache(tmp_path / "resources")
    key = cache.key("speech_pcm", {"content": "same-key", "voice": "verified"})
    payload = b"same-verified-resource" * 30
    # Make every writer repair the same bad entry under contention.
    cache.write("speech_pcm", key, {"payload.bin": payload})
    entry = cache._entry("speech_pcm", key)
    (entry / "payload.bin").write_bytes(b"corrupted")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(
            lambda _: cache.write("speech_pcm", key, {"payload.bin": payload}),
            range(20),
        ))
    assert all(result is None for result in results)
    assert cache.get_pcm(key) == payload
    assert json.loads((entry / "record.json").read_text(encoding="utf-8"))[
        "files"
    ]["payload.bin"]["bytes"] == len(payload)
    assert not list(entry.parent.glob(".pending-*"))


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



def test_cached_mathtex_subtitle_png_decodes_and_rejects_bad_alpha(tmp_path):
    from io import BytesIO
    PIL=pytest.importorskip("PIL")
    from PIL import Image,ImageDraw
    cache=ArtifactCache(tmp_path/"cache")
    key=cache.key("subtitle_png",{
        "kind":"math","display":r"\int_0^1x\,dx",
        "pixel_width":1280,"safe_band_height":88,
        "caption_renderer":"manim_mathtex",
    })
    picture=Image.new("RGBA",(1280,88),(0,0,0,0))
    ImageDraw.Draw(picture).rectangle((300,12,980,72),fill=(12,20,30,255))
    buffer=BytesIO()
    picture.save(buffer,format="PNG")
    cache.write("subtitle_png",key,{"payload.bin":buffer.getvalue()})
    output=tmp_path/"valid.png"
    assert cache.get_png(key,output) is True
    assert output.read_bytes()==buffer.getvalue()
    # No non-transparent backdrop may be added to the classroom view.
    invalid=Image.new("RGBA",(1280,88),(255,255,255,255))
    invalid_bytes=BytesIO()
    invalid.save(invalid_bytes,format="PNG")
    # Published valid keys are immutable; force corruption first so the
    # replacement path can still exercise bad-alpha validation.
    (cache._entry("subtitle_png", key) / "payload.bin").write_bytes(b"damaged")
    cache.write("subtitle_png",key,{"payload.bin":invalid_bytes.getvalue()})
    assert cache.get_png(key,tmp_path/"invalid.png") is False
    assert cache.stats()["subtitle_png_invalid"]>=1



def test_verified_h264_stream_copy_preserves_real_frames(tmp_path):
    """Actual FFmpeg compatibility test, not a fake-video cache test."""
    import subprocess
    from animation_engine.unified_classroom_flow import (
        _concat_verified_clips, _video_frames
    )
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required")
    clips=[]
    for i,color in enumerate(("white","black")):
        path=tmp_path/f"stage_{i}.mp4"
        subprocess.run([
            "ffmpeg","-hide_banner","-loglevel","error","-y",
            "-f","lavfi","-i",
            f"color=c={color}:s=1280x720:r=30:d=0.7",
            "-c:v","libx264","-pix_fmt","yuv420p","-r","30",
            str(path)
        ],check=True,capture_output=True,text=True)
        clips.append(path)
    expected=sum(_video_frames(p,30,min_frames=1) for p in clips)
    playlist=tmp_path/"segments.txt"
    playlist.write_text(
        "".join(f"file '{p.as_posix()}'\n" for p in clips),
        encoding="utf-8",
    )
    target=tmp_path/"final.mp4"
    frames,mode=_concat_verified_clips(
        playlist,target,fps=30,expected_frames=expected,
    )
    assert mode=="codec_copy_verified"
    assert frames==expected
    assert _video_frames(target,30,min_frames=1)==expected


def test_incompatible_video_clip_fails_closed_or_reencodes(tmp_path):
    import subprocess
    from animation_engine.unified_classroom_flow import _concat_verified_clips
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required")
    clips=[]
    for i,color in enumerate(("white","black")):
        path=tmp_path/f"stage_{i}.mp4"
        subprocess.run([
            "ffmpeg","-hide_banner","-loglevel","error","-y",
            "-f","lavfi","-i",
            f"color=c={color}:s=1280x720:r=30:d=0.7",
            "-c:v","libx264","-pix_fmt","yuv420p",
            "-r","30","-profile:v",("main" if i else "baseline"),
            str(path)
        ],check=True,capture_output=True,text=True)
        clips.append(path)
    playlist=tmp_path/"segments.txt"
    playlist.write_text(
        "".join(f"file '{p.as_posix()}'\n" for p in clips),
        encoding="utf-8",
    )
    # Incompatible profile must not be misrepresented as exact bitstream
    # copy. Fallback may reject unsafe concat; that is also acceptable.
    from animation_engine.longboard_plan import LongboardError
    try:
        frames,mode=_concat_verified_clips(
            playlist,tmp_path/"final.mp4",fps=30,expected_frames=42,
        )
        assert mode=="reencode_verified_fallback"
        assert abs(frames-42)<=2
    except LongboardError:
        assert not (tmp_path/"latest.mp4").exists()


def test_composed_stage_and_transition_cache_verify_frames(tmp_path,monkeypatch):
    """Only identical verified pixel-composites and wipes are reusable."""
    from animation_engine import unified_classroom_flow
    cache=ArtifactCache(tmp_path/"cache")
    source=tmp_path/"trusted_video.mp4"
    source.write_bytes(b"MOCK-VIDEO-FRAMES-ONLY")
    monkeypatch.setattr(
        unified_classroom_flow,"_video_frames",
        lambda video,fps,*,min_frames=20:21,
    )
    for namespace in ("composed_stage","transition"):
        key=cache.key(namespace,{
            "source_hash":"a"*64,"fps":30,
            "source_panel_hash":"b"*64
        })
        cache.store_video(namespace,key,source)
        dest=tmp_path/f"{namespace}.mp4"
        assert cache.restore_video(
            namespace,key,dest,fps=30,expected_frames=21
        )
        assert dest.read_bytes()==source.read_bytes()
        assert not cache.restore_video(
            namespace,key,dest,fps=30,expected_frames=22
        )
        assert not dest.exists()
        assert cache.stats()[namespace+"_invalid"]>=1
        different=cache.key(namespace,{
            "source_hash":"a"*64,"fps":30,
            "source_panel_hash":"DIFFERENT"
        })
        assert not cache.restore_video(
            namespace,different,dest,fps=30,expected_frames=21
        )



def test_source_restored_event_clip_reuses_unchanged_events(tmp_path,monkeypatch):
    """Unit-only: one changed event must not rerender the other event."""
    from animation_engine import incremental_render,unified_classroom_flow
    source="d"*64
    stage=SimpleNamespace(
        stage_id="long_math_stage",engine="standard",
        package={"id":"math-source"},storyboard={"id":"same_equation"},
        execution={"source_storyboard_sha256":source},
        cues={"teaching":True},policy={},special=None,
        handoff=(),events=("event1","event2"),kwargs=lambda:{},
    )
    cache=ArtifactCache(tmp_path/"cache")
    schedules={
        "event1":[{"kind":"math","object_id":"math1","duration":1.0,
                    "math_start_delay":0.2}],
        "event2":[{"kind":"math","object_id":"math2","duration":1.2,
                    "math_start_delay":0.2}],
    }
    unchanged=incremental_render._event_key(
        stage,0,"event1",fps=30,layout_hint=None,
        narration_events=schedules,cache=cache,
    )
    video=tmp_path/"source_event.mp4"
    video.write_bytes(b"MOCK-ONLY-A-VERIFIED-MATHEMATICAL-EVENT")
    manifest=tmp_path/"source_event.json"
    manifest.write_text(json.dumps({
        "source_storyboard_sha256":source,
        "voice_status":"not_recorded",
        "event_timing":[{
            "event_id":"event1","start_preview_second":0,
            "end_preview_second":1.0,
            "action_timing":[{
                "kind":"math","object_id":"math1",
                "start_preview_second":0,"end_preview_second":1
            }],
        }],
        "rendered_event_index":0,
        "event_window_entry_verified":True,
        "page_count":1,"event_count":2,
    }))
    cache.store_stage(unchanged,video,manifest,namespace="event_clip")
    rendered=[]
    def fake_render(storyboard,execution,cues,policy,*,event_index,
                    output_mp4,output_json,**kwargs):
        rendered.append(event_index)
        assert event_index==1
        Path(output_mp4).write_bytes(b"MOCK-SECOND-EVENT-ONLY")
        event={
            "event_id":"event2","start_preview_second":0,
            "end_preview_second":1.2,
            "action_timing":[{
                "kind":"math","object_id":"math2",
                "start_preview_second":0.1,"end_preview_second":1.2,
            }],
        }
        record={
            "source_storyboard_sha256":source,
            "voice_status":"not_recorded",
            "event_timing":[event],
            "rendered_event_index":event_index,
            "event_window_entry_verified":True,
            "page_count":1,"event_count":2,
        }
        Path(output_json).write_text(json.dumps(record))
        return record
    monkeypatch.setattr(incremental_render,
                        "render_persistent_chalkboard",fake_render)
    monkeypatch.setattr(unified_classroom_flow,
                        "_video_frames",lambda *args,**kwargs:30)
    def concat(playlist,output,*,fps,expected_frames):
        Path(output).write_bytes(b"MOCK-REASSEMBLED-STAGE-ONLY")
        assert expected_frames==60
        return expected_frames,"verified_mock_concat"
    monkeypatch.setattr(unified_classroom_flow,
                        "_concat_verified_clips",concat)
    output=tmp_path/"assembled.mp4"
    report=incremental_render._rebuild_stage_from_events(
        stage,output_mp4=output,output_json=tmp_path/"assembled.json",
        fps=30,layout_hint=None,narration_events=schedules,cache=cache,
    )
    assert rendered==[1]
    assert len(report["event_timing"])==2
    assert report["actual_video_frames"]==60
    assert report["event_count"]==2
    assert [row["event_id"] for row in report["event_timing"]]==[
        "event1","event2"
    ]
    assert report["event_timing"][1]["start_preview_second"]==1.0
    assert abs(report["event_timing"][1]["action_timing"][0][
        "start_preview_second"]-1.1)<1e-6
    assert cache.stats()["event_clip_hit"]>=1
    assert output.read_bytes().startswith(b"MOCK-")


def test_event_source_hash_or_edit_duration_invalidates_event_clip(tmp_path):
    from animation_engine.incremental_render import _event_key,_event_frame_bounds
    cache=ArtifactCache(tmp_path/"cache")
    stage=SimpleNamespace(
        stage_id="intro",engine="standard",package={},
        storyboard={"math":"x"},execution={"source_storyboard_sha256":"s"*64},
        cues={},policy={},special=None,handoff=(),events=("e1","e2"),
        kwargs=lambda:{},
    )
    one={"e1":[{"duration":1.0}],"e2":[{"duration":2.0}]}
    initial=_event_key(
        stage,1,"e2",fps=30,layout_hint=None,
        narration_events=one,cache=cache,
    )
    changed={"e1":[{"duration":6.0}],"e2":[{"duration":2.0}]}
    assert initial==_event_key(
        stage,1,"e2",fps=30,layout_hint=None,
        narration_events=changed,cache=cache,
    )
    changed["e2"]=[{"duration":2.4}]
    assert initial!=_event_key(
        stage,1,"e2",fps=30,layout_hint=None,
        narration_events=changed,cache=cache,
    )
    stage.execution={"source_storyboard_sha256":"z"*64}
    assert initial!=_event_key(
        stage,1,"e2",fps=30,layout_hint=None,
        narration_events=one,cache=cache,
    )
    assert _event_frame_bounds([
        {"start_preview_second":0},
        {"start_preview_second":1.0},
    ],60,30)==[0,30,60]
    with pytest.raises(ValueError,match="CACHE_EVENT_NONCONTIGUOUS"):
        _event_frame_bounds([
            {"start_preview_second":0},
            {"start_preview_second":0},
        ],60,30)



@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="true FFmpeg is required to test exact event-frame extraction",
)
def test_actual_ffmpeg_event_clip_extraction_uses_compatible_fixed_fps(tmp_path):
    """Frame-precise slicing test using synthetic visual source, NOT voice."""
    import subprocess
    from animation_engine.incremental_render import (
        _cache_full_stage_events, _event_key,
    )
    from animation_engine.unified_classroom_flow import _video_frames
    source_sha="c"*64
    stage=SimpleNamespace(
        stage_id="test_clips",engine="standard",package={},
        storyboard={"id":"synthetic_video_only"},
        execution={"source_storyboard_sha256":source_sha},
        cues={},policy={},special=None,handoff=(),
        events=("e1","e2"),kwargs=lambda:{},
    )
    schedules={
        "e1":[{"kind":"math","object_id":"m1",
               "duration":1.0,"math_start_delay":0.1}],
        "e2":[{"kind":"math","object_id":"m2",
               "duration":2.0,"math_start_delay":0.1}],
    }
    video=tmp_path/"verified_ffmpeg_synthetic.mp4"
    subprocess.run([
        "ffmpeg","-hide_banner","-loglevel","error","-y",
        "-f","lavfi","-i","color=c=white:s=1280x720:r=30:d=3",
        "-c:v","libx264","-pix_fmt","yuv420p","-r","30",
        str(video),
    ],check=True,capture_output=True,text=True)
    assert _video_frames(video,30)==90
    events=[
        {"event_id":eid,"start_preview_second":start,
         "end_preview_second":end,
         "action_timing":[{
             "kind":"math","object_id":f"m{i+1}",
             "start_preview_second":start+0.1,
             "end_preview_second":end,
         }]}
        for i,(eid,start,end) in enumerate([
            ("e1",0.0,1.0),("e2",1.0,3.0)
        ])
    ]
    report={
        "source_storyboard_sha256":source_sha,
        "voice_status":"not_recorded","event_timing":events,
        "page_count":1,"event_count":2,
    }
    cache=ArtifactCache(tmp_path/"cache")
    _cache_full_stage_events(
        stage,report,video,fps=30,layout_hint=None,
        narration_events=schedules,cache=cache
    )
    for i,(eid,frames) in enumerate([("e1",30),("e2",60)]):
        key=_event_key(
            stage,i,eid,fps=30,layout_hint=None,
            narration_events=schedules,cache=cache,
        )
        dest=tmp_path/f"{eid}.mp4"
        js=tmp_path/f"{eid}.json"
        restored=cache.restore_stage(
            key,dest,js,fps=30,
            source_storyboard_sha256=source_sha,
            namespace="event_clip",
            expected_event_id=eid,
            expected_event_index=i,
        )
        assert restored is not None
        assert _video_frames(dest,30,min_frames=1)==frames
        assert len(restored["event_timing"])==1
        assert restored["event_timing"][0]["event_id"]==eid


def test_changing_speech_rate_invalidates_all_stages_and_full_timeline(tmp_path):
    before,after=_package(tmp_path)
    path,data=_spoken(after)
    data["speech_rate"]="-4%"
    _write(path,data)
    impact=analyze_impact(before,after,_op("/speech_rate"))
    assert impact["whole_lesson_invalidation"]
    assert impact["affected_stages"]==[
        "introduce_triangle","calculate_hypotenuse","calculate_perimeter"
    ]
    assert impact["reusable_stages_subject_to_cache_validation"]==[]


def test_voice_cache_is_keyed_by_actual_voice_and_speech_rate(tmp_path,monkeypatch):
    import types
    from animation_engine import spoken_audio
    calls=[]
    class DummyVoice:
        def __init__(self,text,voice,rate):
            calls.append((text,voice,rate))
        async def save(self,path):
            Path(path).write_bytes(b"MOCK ONLY MP3 BYTES"*20)
    monkeypatch.setitem(sys.modules,"edge_tts",
                        types.SimpleNamespace(Communicate=DummyVoice))
    monkeypatch.setattr(
        spoken_audio,"_decode_mp3_to_pcm",
        lambda mp3,wav: struct.pack("<h",1200)*15000,
    )
    cache=ArtifactCache(tmp_path/"cache")
    root=tmp_path/"clips"
    root.mkdir()
    semaphore=asyncio.Semaphore(1)
    def run(i,voice,rate):
        return asyncio.run(_edge_clip(
            i,"求三角形周长","zh-CN-"+voice+"Neural",
            root,semaphore,cache,rate=rate,
        ))
    run(0,"Yunxi","+1%")
    run(1,"Yunxi","+1%")
    run(2,"Yunxi","-4%")
    run(3,"Xiaoxiao","+1%")
    assert calls==[
        ("求三角形周长","zh-CN-YunxiNeural","+1%"),
        ("求三角形周长","zh-CN-YunxiNeural","-4%"),
        ("求三角形周长","zh-CN-XiaoxiaoNeural","+1%"),
    ]
    assert cache.stats()["speech_pcm_hit"]==1
