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


def test_auth_cookie_stream_compatible_without_browser_header(tmp_path,monkeypatch):
    monkeypatch.setenv("WEIGUANG_API_TOKEN","test-secret-long-private-token")
    app=create_app(data_dir=tmp_path/"private",local_dev=True,eager=True)
    client=TestClient(app)
    assert client.get("/api/v1/lessons").status_code==401
    assert client.post("/api/v1/auth/login",
        json={"token":"wrong"}).status_code==401
    ok=client.post("/api/v1/auth/login",
        json={"token":"test-secret-long-private-token"})
    assert ok.status_code==200
    cookie=ok.headers.get("set-cookie","")
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert client.get("/api/v1/lessons").status_code==200
    denied=client.post("/api/v1/projects",json={"title":"cross origin"},
        headers={"Origin":"https://evil.example"})
    assert denied.status_code==403
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/lessons").status_code==401


def test_renaming_does_not_invalidate_video_source_and_changed_fps_does(studio):
    client,source,archive=studio
    ident=create_verified(studio)
    l=client.get(f"/api/v1/lessons/{ident}").json()
    rename=client.patch(f"/api/v1/videos/{ident}",
        json={"title":"重命名但不修改数学"})
    assert rename.status_code==200
    assert rename.json()["revision"]==l["revision"]
    changed=client.patch(f"/api/v1/lessons/{ident}",
        json={"fps":30})
    assert changed.status_code==200
    assert changed.json()["status"]=="draft"
    assert changed.json()["revision"]==l["revision"]+1
    # Older data remains archived, re-upload is not stuck forever.
    reupload=client.post(f"/api/v1/lessons/{ident}/package",
        files={"file":("reviewed.zip",archive,"application/zip")})
    assert reupload.status_code==200,reupload.text
    archive_dir=Path(client.app.state.root)/"lessons"/ident/"previous_packages"
    assert archive_dir.exists() and list(archive_dir.iterdir())



def test_compiled_curriculum_approval_to_reviewed_video_and_download(studio,tmp_path):
    from test_compiler import curriculum_fixture
    from weiguang_backend.models import Lesson
    client,_,_=studio
    source,candidate=curriculum_fixture(tmp_path)
    created=client.post("/api/v1/lessons",json={
        "title":"自动候选经人工审核的课程",
        "problem":source["problem"],
        "reference_solution":source["reference_solution"],
    })
    assert created.status_code==201,created.text
    ident=created.json()["id"]
    with client.app.state.SessionLocal() as db:
        lesson=db.get(Lesson,ident)
        lesson.status="curriculum_review_pending"
        db.commit()
    basedir=Path(client.app.state.root)/"lessons"/ident
    basedir.mkdir(parents=True,exist_ok=True)
    (basedir/"curriculum_candidate.json").write_text(
        json.dumps(candidate,ensure_ascii=False),encoding="utf-8",
    )
    payload=client.get(f"/api/v1/lessons/{ident}/curriculum")
    assert payload.status_code==200
    no_review=client.post(f"/api/v1/lessons/{ident}/curriculum/approve",
        json={"reviewer":"teacher","confirmed":False})
    assert no_review.status_code==422
    approved=client.post(f"/api/v1/lessons/{ident}/curriculum/approve",
        json={"reviewer":"teacher","confirmed":True})
    assert approved.status_code==200,approved.text
    assert approved.json()["events"]==10
    script=client.get(f"/api/v1/lessons/{ident}/script")
    assert script.status_code==200,script.text
    accepted=client.post(f"/api/v1/lessons/{ident}/approve",
        json={"reviewer":"teacher","confirmed":True})
    assert accepted.status_code==200,accepted.text
    rendered=client.post(f"/api/v1/lessons/{ident}/render")
    assert rendered.status_code==202,rendered.text
    job=client.get("/api/v1/jobs/"+rendered.json()["id"]).json()
    assert job["status"]=="succeeded",job
    assert client.get(f"/api/v1/videos/{ident}/download").status_code==200


def test_failed_rerender_keeps_old_video_and_all_history_after_source_change(studio):
    from weiguang_backend.models import EditSessionArchive
    client,source,archive=studio
    ident=create_verified(studio)
    first=client.post(f"/api/v1/lessons/{ident}/render")
    assert client.get("/api/v1/jobs/"+first.json()["id"]).json()["status"]=="succeeded"
    with client.app.state.SessionLocal() as db:
        original=db.get(__import__(
            "weiguang_backend.models",fromlist=["Lesson"]
        ).Lesson,ident)
        prior_movie=Path(original.latest_video)
        prior_session=Path(original.session_path)
    assert prior_movie.is_file() and prior_session.exists()
    changed=client.patch(f"/api/v1/lessons/{ident}",json={
        "voice":"zh-CN-XiaoxiaoNeural",
    })
    assert changed.status_code==200,changed.text
    assert changed.json()["status"]=="draft"
    assert client.get(f"/api/v1/videos/{ident}/stream").status_code==404
    # The old artifacts remain stored and indexed for the global export.
    assert prior_movie.is_file() and prior_session.is_dir()
    upload=client.post(f"/api/v1/lessons/{ident}/package",
        files={"file":("reviewed.zip",archive,"application/zip")})
    assert upload.status_code==200,upload.text
    source_file=Path(client.app.state.root)/"lessons"/ident/"package"/"spoken_classroom.json"
    assert json.loads(source_file.read_text(encoding="utf-8"))["voice"]=="zh-CN-XiaoxiaoNeural"
    script=client.get(f"/api/v1/lessons/{ident}/script")
    assert script.status_code==200,script.text
    approved=client.post(f"/api/v1/lessons/{ident}/approve",json={
        "reviewer":"source-reviewer","confirmed":True,
    })
    assert approved.status_code==200,approved.text
    second=client.post(f"/api/v1/lessons/{ident}/render")
    assert second.status_code==202,second.text
    job=client.get("/api/v1/jobs/"+second.json()["id"]).json()
    assert job["status"]=="succeeded",job
    with client.app.state.SessionLocal() as db:
        lesson=db.get(__import__(
            "weiguang_backend.models",fromlist=["Lesson"]
        ).Lesson,ident)
        assert Path(lesson.latest_video)!=prior_movie
        assert Path(lesson.session_path)!=prior_session
        entries=list(db.query(EditSessionArchive).filter_by(lesson_id=ident))
        assert len(entries)==2
    assert prior_movie.is_file()
    assert len(client.get("/api/v1/system/edit-history/export").json()["sessions"])==2


def test_api_rejects_unsupported_voice_and_phantom_ai_teacher(tmp_path,monkeypatch):
    monkeypatch.delenv("WEIGUANG_TEACHER_ENABLED",raising=False)
    monkeypatch.delenv("MATH_TEACHER_MODEL",raising=False)
    monkeypatch.delenv("MATH_TEACHER_API_KEY",raising=False)
    client=TestClient(create_app(data_dir=tmp_path/"store",local_dev=True,eager=True))
    bad=client.post("/api/v1/lessons",json={
        "title":"非法音色","problem":"1+1","reference_solution":"2",
        "voice":"nonexistent-voice",
    })
    assert bad.status_code==422
    item=client.post("/api/v1/lessons",json={
        "title":"等待模型","problem":"1+1","reference_solution":"2",
    }).json()
    assert client.post(f"/api/v1/lessons/{item['id']}/prepare").status_code==409
