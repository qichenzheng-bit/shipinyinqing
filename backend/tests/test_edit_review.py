"""Review candidates are durable, digest-bound and never silently rendered."""
import json
from pathlib import Path

import pytest

from test_web_flow import create_verified, fake_render, studio
from weiguang_backend.edit_review import (
    mark_edit_review, prepare_edit_review, render_approved_edit,
    reject_edit_review, view_edit_review,
)
from animation_engine.iterative_edit_ops import EditEngineError


def _sample_plan(instruction,package,history):
    document=json.loads((package/"spoken_classroom.json").read_text(encoding="utf-8"))
    last=len(document["events"])-1
    original=document["events"][last]["spans"][0]["parts"][0]["value"]
    return {
        "schema_version":"1.0","model":"fake-review-model",
        "requirements":[{
            "id":"req1","instruction":instruction,
            "target":"结尾口播","operation_ids":["op1"],
        }],
        "operations":[{
            "id":"op1","file":"spoken_classroom.json",
            "pointer":f"/events/{last}/spans/0/parts/0/value",
            "action":"set","value":original+"再简洁说明积分变量。",
        }],
    }


def _fixture(studio):
    client,_,_=studio
    ident=create_verified(studio)
    started=client.post(f"/api/v1/lessons/{ident}/render")
    assert started.status_code==202
    with client.app.state.SessionLocal() as db:
        from weiguang_backend.models import Lesson
        lesson=db.get(Lesson,ident)
        session=Path(lesson.session_path)
    return client,ident,session


def _test_renderer(package,movie,manifest,subtitles,*,fps,adaptive):
    return fake_render(
        Path(package)/"spoken_classroom.json",
        output_mp4=movie,output_json=manifest,output_srt=subtitles,
        fps=fps,adaptive=adaptive,
    )


def test_reviewed_candidate_waits_and_can_be_completed_after_restart(studio):
    client,ident,session=_fixture(studio)
    before=(session/"latest.mp4").read_bytes()
    proposal=prepare_edit_review(
        session,"把结尾再讲简洁一些",agent=_sample_plan,
    )
    assert proposal["status"]=="review_pending"
    path=Path(proposal["review_path"])
    assert path.is_dir()
    assert view_edit_review(path)["status"]=="pending"
    assert (session/"latest.mp4").read_bytes()==before
    with pytest.raises(EditEngineError,match="EDIT_REVIEW_STALE_REVISION"):
        mark_edit_review(path,reviewer="老师",confirmed=True,current_revision=99)
    mark_edit_review(path,reviewer="老师",confirmed=True,current_revision=0)
    outcome=render_approved_edit(
        session,path,renderer=_test_renderer,media_check=lambda *_:None,
    )
    assert outcome["status"]=="preview_ready",outcome
    assert outcome["revision"]==1
    assert (session/"versions"/"0001"/"movie.mp4").is_file()
    assert (session/"latest.mp4").is_file()


def test_reviewed_candidate_reject_or_tamper_never_updates_movie(studio):
    client,ident,session=_fixture(studio)
    before=(session/"latest.mp4").read_bytes()
    pending=Path(prepare_edit_review(
        session,"修改总结",agent=_sample_plan,
    )["review_path"])
    changed=pending/"package"/"spoken_classroom.json"
    changed.write_text(changed.read_text(encoding="utf-8")+"\n",encoding="utf-8")
    with pytest.raises(EditEngineError,match="EDIT_REVIEW_CANDIDATE_CHANGED"):
        mark_edit_review(pending,reviewer="老师",confirmed=True,current_revision=0)
    pending2=Path(prepare_edit_review(
        session,"修改最后一步",agent=_sample_plan,
    )["review_path"])
    reject_edit_review(pending2)
    with pytest.raises(EditEngineError,match="EDIT_REVIEW_INVALID"):
        render_approved_edit(session,pending2,renderer=_test_renderer,
                             media_check=lambda *_:None)
    assert (session/"latest.mp4").read_bytes()==before



def test_http_pending_approve_render_and_reject_are_fully_connected(
        studio,monkeypatch):
    import weiguang_backend.edit_review as edit_review_module
    from weiguang_backend.models import EditRecord,Lesson
    client,ident,session=_fixture(studio)
    first=prepare_edit_review(
        session,"结尾讲清楚积分变量",agent=_sample_plan,
    )
    with client.app.state.SessionLocal() as db:
        lesson=db.get(Lesson,ident)
        row=EditRecord(
            lesson_id=ident,original_instruction="结尾讲清楚积分变量",
            status="review_pending",review_path=first["review_path"],
            source_revision=lesson.revision,
        )
        db.add(row);db.commit();db.refresh(row)
        edit_id=row.id
    pending=client.get(f"/api/v1/videos/{ident}/edits/pending")
    assert pending.status_code==200,pending.text
    assert pending.json()["pending"]["edit_id"]==edit_id
    assert pending.json()["pending"]["status"]=="pending"

    original=edit_review_module.render_approved_edit
    def verified_preview(sess,review_path):
        return original(
            sess,review_path,renderer=_test_renderer,
            media_check=lambda *_:None,
        )
    monkeypatch.setattr(edit_review_module,"render_approved_edit",verified_preview)
    response=client.post(
        f"/api/v1/videos/{ident}/edits/{edit_id}/approve",
        json={"reviewer":"实际数学审核人","confirmed":True},
    )
    assert response.status_code==202,response.text
    result=client.get("/api/v1/jobs/"+response.json()["job"]["id"]).json()
    assert result["status"]=="succeeded",result
    assert client.get(f"/api/v1/videos/{ident}/edits/pending").json()["pending"] is None
    with client.app.state.SessionLocal() as db:
        lesson=db.get(Lesson,ident)
        assert Path(lesson.latest_video).parts[-3:]==("versions","0001","movie.mp4")
        row=db.get(EditRecord,edit_id)
        assert row.status=="preview_ready"
        assert row.reviewer=="实际数学审核人"

    another=prepare_edit_review(
        session,"结尾可以再精炼",agent=_sample_plan,
    )
    with client.app.state.SessionLocal() as db:
        lesson=db.get(Lesson,ident)
        row=EditRecord(
            lesson_id=ident,original_instruction="结尾可以再精炼",
            status="review_pending",review_path=another["review_path"],
            source_revision=lesson.revision,
        )
        db.add(row);db.commit();db.refresh(row)
        second_id=row.id
    rejected=client.post(f"/api/v1/videos/{ident}/edits/{second_id}/reject")
    assert rejected.status_code==200
    assert rejected.json()["status"]=="rejected"
    assert client.get(f"/api/v1/videos/{ident}/edits/pending").json()["pending"] is None
    assert (session/"versions"/"0001"/"movie.mp4").is_file()
