"""API ↔ real course contracts ↔ edited session smoke, without MP4 rendering.

Injected artifacts are deliberately NOT playable teaching movies. Production
always uses render_spoken_classroom and authentic media verification.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from animation_engine.spoken_classroom import checked_spoken
from animation_engine.iterative_edit_ops import validate_teaching_package

sys.path.insert(0,str(Path(__file__).resolve().parents[2] /
    "animation_engine" / "tests" / "fixtures"))
from build_novel_substitution_integral import build

from weiguang_backend.main import create_app


def fake_report(package):
    checked=validate_teaching_package(Path(package),adaptive=False)
    return {
        "source_spoken_sha256":checked["source_spoken_sha256"],
        "source_flow_sha256":checked["source_flow_sha256"],
        "voice_status":"real_edge_neural_pcm_verified",
        "subtitle_status":"actual_tts_phrase_aligned",
        "math_caption_renderer":"true_manim_mathtex",
        "voiced_action_count":checked["spoken_actions"],
        "source_narration_action_count":checked["spoken_actions"],
        "fabricated_voice_or_subtitle_count":0,
        "audio_verification":{"sample_rate":24000,"channels":1},
    }


def fake_render(source,*,output_mp4,output_json,output_srt,fps,adaptive):
    assert fps==60 and adaptive is False
    Path(output_mp4).write_bytes(b"TEST_ONLY_NOT_PLAYABLE_AV")
    report=fake_report(Path(source).parent)
    Path(output_json).write_text(json.dumps(report),encoding="utf-8")
    Path(output_srt).write_text("TEST_ONLY",encoding="utf-8")
    return report


def fake_edit(session,instruction):
    from animation_engine.iterative_edit_engine import run_edit
    def plan(_,package,history):
        source=json.loads((package/"spoken_classroom.json").read_text(encoding="utf-8"))
        last=len(source["events"])-1
        original=source["events"][last]["spans"][0]["parts"][0]["value"]
        return {
            "schema_version":"1.0","model":"reviewed-test-stub",
            "requirements":[{"id":"r1","instruction":instruction,
                             "target":"归纳","operation_ids":["o1"]}],
            "operations":[{
                "id":"o1","file":"spoken_classroom.json",
                "pointer":f"/events/{last}/spans/0/parts/0/value",
                "action":"set",
                "value":original+"另外，检查新积分限。",
            }],
        }
    def renderer(package,movie,manifest,subtitles,*,fps,adaptive):
        return fake_render(
            Path(package)/"spoken_classroom.json",
            output_mp4=movie,output_json=manifest,output_srt=subtitles,
            fps=fps,adaptive=adaptive,
        )
    return run_edit(
        session,instruction,plan,renderer=renderer,
        math_reviewer=lambda *args: True,
        script_reviewer=lambda *args: True,
        media_check=lambda *_: None,
    )


@pytest.fixture
def studio(tmp_path):
    sample=tmp_path/"source"
    build(sample)
    teacher=json.loads((sample/"integration"/"teaching_package.json").read_text(encoding="utf-8"))
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,"w") as archive:
        for f in sample.rglob("*"):
            if f.is_file():
                archive.write(f,f.relative_to(sample).as_posix())
    app=create_app(
        data_dir=tmp_path/"store",
        local_dev=True,eager=True,renderer=fake_render,
        verify_media=lambda *_: None,edit_runner=fake_edit,
    )
    client=TestClient(app)
    return client,teacher["source"],buffer.getvalue()


def create_verified(studio):
    client,source,archive=studio
    lesson=client.post("/api/v1/lessons",json={
        "title":"积分 · 端到端测试","problem":source["problem"],
        "reference_solution":source["reference_solution"],
    })
    assert lesson.status_code==201,lesson.text
    ident=lesson.json()["id"]
    upload=client.post(f"/api/v1/lessons/{ident}/package",
        files={"file":("approved.zip",archive,"application/zip")})
    assert upload.status_code==200,upload.text
    assert upload.json()["events"]==10
    script=client.get(f"/api/v1/lessons/{ident}/script")
    assert script.status_code==200 and "完整口播" in script.json()["script"]
    approval=client.post(f"/api/v1/lessons/{ident}/approve",json={
        "reviewer":"course-teacher","confirmed":True,
    })
    assert approval.status_code==200,approval.text
    return ident


def test_full_api_course_review_video_edit_feedback_export(studio):
    client,source,archive=studio
    ident=create_verified(studio)
    started=client.post(f"/api/v1/lessons/{ident}/render")
    assert started.status_code==202,started.text
    job=client.get("/api/v1/jobs/"+started.json()["id"]).json()
    assert job["status"]=="succeeded",job
    video=client.get(f"/api/v1/videos/{ident}/stream")
    assert video.status_code==200 and video.content==b"TEST_ONLY_NOT_PLAYABLE_AV"
    dl=client.get(f"/api/v1/videos/{ident}/download")
    assert dl.status_code==200
    rename=client.patch(f"/api/v1/videos/{ident}",json={"title":"积分教学修改版"})
    assert rename.status_code==200
    task=client.post(f"/api/v1/videos/{ident}/edits",json={
        "instruction":"最后总结再简短说明积分限",
    })
    assert task.status_code==202,task.text
    job2=client.get("/api/v1/jobs/"+task.json()["job"]["id"]).json()
    assert job2["status"]=="succeeded",job2
    confirm=client.post(f"/api/v1/videos/{ident}/feedback",json={
        "feedback":"这次满意","satisfied":True,
    })
    assert confirm.status_code==200,confirm.text
    export=client.get("/api/v1/system/edit-history/export")
    assert export.status_code==200
    payload=export.json()
    assert payload["mode"]=="weiguang_all_edit_history"
    assert len(payload["sessions"])==1
    assert payload["sessions"][0]["session"]["rounds"][0]["status"]=="accepted"
    assert payload["api_attempts"][0]["original_instruction"].startswith("最后总结")
    deleted=client.post("/api/v1/videos/batch-delete",json={"ids":[ident]})
    assert deleted.status_code==200
    assert client.get("/api/v1/lessons").json()==[]
    assert len(client.get("/api/v1/trash").json())==1
    restored=client.post("/api/v1/trash/restore",json={"ids":[ident]})
    assert restored.status_code==200
    assert client.get(f"/api/v1/lessons/{ident}").status_code==200
    assert client.get("/").status_code==200
    assert client.get("/styles.css").status_code==200
    assert client.get("/app.js").status_code==200
    assert client.get("/logo.svg").status_code==200


def test_no_false_approval_no_download_before_render(studio):
    client,source,archive=studio
    lesson=client.post("/api/v1/lessons",json={
        "title":"未审核课程","problem":source["problem"],
        "reference_solution":source["reference_solution"],
    }).json()
    ident=lesson["id"]
    assert client.post(f"/api/v1/lessons/{ident}/render").status_code==409
    assert client.get(f"/api/v1/videos/{ident}/stream").status_code==404
    assert client.post(f"/api/v1/videos/{ident}/edits",
        json={"instruction":"修改"}).status_code==409


def test_multi_delete_is_atomic_and_no_zip_escape(studio):
    client,source,archive=studio
    ids=[]
    for i in range(2):
        result=client.post("/api/v1/lessons",json={
            "title":f"课程{i}","problem":source["problem"],
            "reference_solution":source["reference_solution"],
        })
        ids.append(result.json()["id"])
    assert client.post("/api/v1/lessons/batch-delete",
        json={"ids":[ids[0],"not-existing"]}).status_code==404
    assert len(client.get("/api/v1/lessons").json())==2
    assert client.post("/api/v1/lessons/batch-delete",
        json={"ids":ids}).json()["count"]==2
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,"w") as f:
        f.writestr("../escape.json","{}")
    third=client.post("/api/v1/lessons",json={
        "title":"不安全ZIP","problem":source["problem"],
        "reference_solution":source["reference_solution"],
    }).json()["id"]
    rejected=client.post(f"/api/v1/lessons/{third}/package",
        files={"file":("unsafe.zip",payload.getvalue(),"application/zip")})
    assert rejected.status_code==422
