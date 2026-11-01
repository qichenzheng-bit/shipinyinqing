"""WeiGuang Math FastAPI: CRUD, review, queue, video, editing, global export.

The API never treats draft mathematics or test-only media as a real video.
Use `WEIGUANG_LOCAL_DEV=1` only for loopback development; on a public server
set WEIGUANG_API_TOKEN and terminate TLS through a trusted reverse proxy.
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import (
    APIRouter, Depends, FastAPI, File, HTTPException, Query, Request,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from .bridge import (
    approve_script, export_script, extract_engine_package,
    initialize_edit, render_package, run_real_edit,
)
from .models import Base, EditRecord, Job, Lesson, Project, now


def describe_lesson(lesson: Lesson):
    return {
        "id":lesson.id,"project_id":lesson.project_id,
        "title":lesson.title,"problem":lesson.problem,
        "reference_solution":lesson.reference_solution,
        "status":lesson.status,"revision":lesson.revision,
        "voice":lesson.voice,"fps":lesson.fps,
        "has_video":bool(lesson.latest_video),
        "created_at":lesson.created_at.isoformat(),
        "updated_at":lesson.updated_at.isoformat(),
    }


def describe_job(job: Job):
    return {
        "id":job.id,"lesson_id":job.lesson_id,"kind":job.kind,
        "status":job.status,"phase":job.phase,"error":job.error,
        "expected_revision":job.expected_revision,
        "created_at":job.created_at.isoformat(),
    }


class ProjectCreate(BaseModel):
    title: str=Field(min_length=1,max_length=180)


class LessonCreate(BaseModel):
    title: str=Field(min_length=1,max_length=180)
    problem: str=Field(min_length=1,max_length=20000)
    reference_solution: str=Field(min_length=1,max_length=120000)
    project_id: str | None=None
    voice: str="zh-CN-YunxiNeural"
    fps: int=Field(default=60,ge=8,le=60)


class Rename(BaseModel):
    title: str=Field(min_length=1,max_length=180)


class DeleteBatch(BaseModel):
    ids: list[str]=Field(min_length=1,max_length=200)


class Review(BaseModel):
    reviewer: str=Field(min_length=1,max_length=120)
    confirmed: bool=False


class EditRequest(BaseModel):
    instruction: str=Field(min_length=1,max_length=12000)


class Feedback(BaseModel):
    feedback: str=Field(min_length=1,max_length=2000)
    satisfied: bool=False


def _trusted(name: str | None):
    if not name:
        return None
    module,_,func=name.partition(":")
    if not module or not func:
        raise ValueError("REVIEWER_CONFIG_INVALID")
    candidate=getattr(importlib.import_module(module),func)
    if not callable(candidate):
        raise ValueError("REVIEWER_CONFIG_NOT_CALLABLE")
    return candidate


def create_app(
    *, data_dir: Path | None=None,
    database_url: str | None=None,
    local_dev: bool | None=None,
    eager: bool=False,
    renderer: Callable | None=None,
    verify_media: Callable | None=None,
    edit_runner: Callable | None=None,
) -> FastAPI:
    root=Path(data_dir or os.environ.get("WEIGUANG_STORAGE","./.weiguang_data")).resolve()
    root.mkdir(parents=True,exist_ok=True)
    url=database_url or os.environ.get("DATABASE_URL")
    if not url:
        url="sqlite:///"+(root/"weiguang.db").as_posix()
    engine=create_engine(
        url,pool_pre_ping=True,
        connect_args={"check_same_thread":False} if url.startswith("sqlite:") else {},
    )
    Base.metadata.create_all(engine)
    SessionLocal=sessionmaker(engine,expire_on_commit=False)
    dev=(os.environ.get("WEIGUANG_LOCAL_DEV")=="1" if local_dev is None else local_dev)
    app=FastAPI(title="微光数学视频 API",version="0.1.0")
    app.state.root=root
    app.state.SessionLocal=SessionLocal

    def auth(request: Request):
        key=os.environ.get("WEIGUANG_API_TOKEN","")
        if key:
            import hmac
            supplied=request.headers.get("X-API-Key","")
            if not hmac.compare_digest(supplied,key):
                raise HTTPException(401,"AUTHENTICATION_REQUIRED")
        elif not (dev and request.client and
                  request.client.host in ("127.0.0.1","::1","localhost","testclient","testserver")):
            raise HTTPException(503,"PUBLIC_SERVER_REQUIRES_API_TOKEN")
    api=APIRouter(prefix="/api/v1",dependencies=[Depends(auth)])

    def lesson_get(db, ident: str, *, include_deleted=False) -> Lesson:
        row=db.get(Lesson,ident)
        if row is None or (row.deleted_at is not None and not include_deleted):
            raise HTTPException(404,"LESSON_NOT_FOUND")
        return row

    def lesson_root(ident):
        if len(ident)!=32 or not all(ch in "0123456789abcdef" for ch in ident):
            raise HTTPException(400,"INVALID_LESSON_ID")
        return root/"lessons"/ident

    def job_add(db: Session, lesson: Lesson,kind: str,edit_id=None):
        existing=db.scalars(select(Job).where(
            Job.lesson_id==lesson.id,Job.status.in_(("queued","running"))
        )).first()
        if existing is not None:
            raise HTTPException(409,"LESSON_JOB_ALREADY_ACTIVE")
        job=Job(lesson_id=lesson.id,kind=kind,edit_id=edit_id,
                expected_revision=lesson.revision)
        db.add(job);db.commit();db.refresh(job)
        return job

    def run_job(job_id: str):
        """Celery/eager execution with per-task revision fence."""
        with SessionLocal() as db:
            job=db.get(Job,job_id)
            if job is None or job.status!="queued":
                return
            lesson=lesson_get(db,job.lesson_id)
            if lesson.revision!=job.expected_revision or lesson.deleted_at:
                job.status="failed";job.error="SOURCE_REVISION_CHANGED"
                db.commit();return
            job.status="running";job.phase="验证来源";db.commit()
            lesson_id=lesson.id
            kind=job.kind
            edit_id=job.edit_id
            fps=lesson.fps
            previous_revision=lesson.revision
        try:
            folder=lesson_root(lesson_id)
            if kind=="render":
                with SessionLocal() as db:
                    job=db.get(Job,job_id);job.phase="渲染画面与音频";db.commit()
                movie,manifest,srt,report=render_package(
                    folder/"package",folder/"output",fps=fps,renderer=renderer,
                )
                with SessionLocal() as db:
                    lesson=lesson_get(db,lesson_id)
                    job=db.get(Job,job_id)
                    if lesson.revision!=previous_revision or job.status!="running":
                        raise RuntimeError("STALE_OR_CANCELLED_JOB")
                session=folder/"edit_session"
                if not session.exists():
                    initialize_edit(
                        folder/"package",movie,manifest,session,fps=fps,
                        verify_media=verify_media,
                    )
                with SessionLocal() as db:
                    lesson=lesson_get(db,lesson_id)
                    job=db.get(Job,job_id)
                    if lesson.revision!=previous_revision or job.status!="running":
                        raise RuntimeError("STALE_OR_CANCELLED_JOB")
                    lesson.latest_video=str(movie)
                    lesson.latest_manifest=str(manifest)
                    lesson.session_path=str(session)
                    lesson.revision+=1
                    lesson.status="ready"
                    job.status="succeeded";job.phase="完成"
                    db.commit()
            elif kind=="edit":
                with SessionLocal() as db:
                    job=db.get(Job,job_id)
                    job.phase="执行微调";db.commit()
                    record=db.get(EditRecord,edit_id)
                    instruction=record.original_instruction
                    lesson=lesson_get(db,lesson_id)
                    session=Path(lesson.session_path)
                if edit_runner is not None:
                    outcome=edit_runner(session,instruction)
                else:
                    config=Path(os.environ.get("WEIGUANG_EDIT_AI_CONFIG",""))
                    outcome=run_real_edit(
                        session,instruction,ai_config=config,
                        math_reviewer=_trusted(os.environ.get("WEIGUANG_MATH_REVIEWER")),
                        script_reviewer=_trusted(os.environ.get("WEIGUANG_SCRIPT_REVIEWER")),
                    )
                if outcome.get("status")!="preview_ready":
                    raise RuntimeError(outcome.get("error") or "EDIT_NOT_APPROVED")
                with SessionLocal() as db:
                    lesson=lesson_get(db,lesson_id);job=db.get(Job,job_id)
                    record=db.get(EditRecord,edit_id)
                    if lesson.revision!=previous_revision or job.status!="running":
                        raise RuntimeError("STALE_OR_CANCELLED_JOB")
                    lesson.revision+=1
                    lesson.status="ready"
                    lesson.latest_video=str(session/"latest.mp4")
                    lesson.latest_manifest=str(session/"latest_manifest.json")
                    record.status="preview_ready"
                    job.status="succeeded";job.phase="完成"
                    db.commit()
            else:
                raise ValueError("UNKNOWN_JOB_KIND")
        except Exception as exc:
            with SessionLocal() as db:
                job=db.get(Job,job_id)
                if job and job.status!="cancelled":
                    job.status="failed";job.phase="失败"
                    job.error=f"{type(exc).__name__}: {str(exc)[:300]}"
                if edit_id:
                    rec=db.get(EditRecord,edit_id)
                    if rec:
                        rec.status="failed"
                        rec.error=(job.error if job else "UNKNOWN")
                db.commit()

    app.state.run_job=run_job

    def dispatch(job_id):
        if eager:
            run_job(job_id)
        else:
            from .worker import celery_app
            celery_app.send_task("weiguang.run_job",args=[job_id])

    @app.get("/health")
    def health():
        return {"status":"ok","service":"weiguang-math"}

    @api.get("/projects")
    def projects():
        with SessionLocal() as db:
            return [{"id":p.id,"title":p.title} for p in db.scalars(
                select(Project).where(Project.deleted_at.is_(None)).order_by(Project.created_at.desc())
            )]

    @api.post("/projects",status_code=201)
    def project_create(data: ProjectCreate):
        with SessionLocal() as db:
            p=Project(title=data.title)
            db.add(p);db.commit();return {"id":p.id,"title":p.title}

    @api.patch("/projects/{id}")
    def project_rename(id: str,data: Rename):
        with SessionLocal() as db:
            p=db.get(Project,id)
            if not p or p.deleted_at:raise HTTPException(404,"PROJECT_NOT_FOUND")
            p.title=data.title;db.commit();return {"id":p.id,"title":p.title}

    @api.delete("/projects/{id}")
    def project_delete(id: str):
        with SessionLocal() as db:
            p=db.get(Project,id)
            if not p or p.deleted_at:raise HTTPException(404,"PROJECT_NOT_FOUND")
            active=db.scalars(select(Job).join(Lesson,Lesson.id==Job.lesson_id).where(
                Lesson.project_id==id,Job.status.in_(("queued","running"))
            )).first()
            if active:raise HTTPException(409,"PROJECT_ACTIVE_JOBS")
            p.deleted_at=now()
            for l in db.scalars(select(Lesson).where(Lesson.project_id==id)):
                l.deleted_at=now()
            db.commit();return {"deleted":[id]}

    @api.get("/lessons")
    def lessons(q: str="",include_deleted: bool=False,
                limit: int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
        with SessionLocal() as db:
            stmt=select(Lesson)
            if not include_deleted:stmt=stmt.where(Lesson.deleted_at.is_(None))
            if q:stmt=stmt.where(Lesson.title.ilike(f"%{q}%"))
            rows=db.scalars(stmt.order_by(Lesson.created_at.desc()).offset(offset).limit(limit))
            return [describe_lesson(l) for l in rows]

    @api.post("/lessons",status_code=201)
    def lesson_create(data: LessonCreate):
        with SessionLocal() as db:
            if data.project_id:
                p=db.get(Project,data.project_id)
                if p is None or p.deleted_at:raise HTTPException(404,"PROJECT_NOT_FOUND")
            l=Lesson(**data.model_dump())
            db.add(l);db.commit();db.refresh(l);return describe_lesson(l)

    @api.get("/lessons/{id}")
    def lesson_read(id: str):
        with SessionLocal() as db:return describe_lesson(lesson_get(db,id))

    @api.patch("/lessons/{id}")
    def lesson_patch(id: str,data: dict):
        allowed={"title","problem","reference_solution","voice","fps"}
        if not data or set(data)-allowed:raise HTTPException(422,"INVALID_UPDATE_FIELDS")
        with SessionLocal() as db:
            l=lesson_get(db,id)
            active=db.scalars(select(Job).where(
                Job.lesson_id==id,Job.status.in_(("queued","running"))
            )).first()
            if active:raise HTTPException(409,"LESSON_ACTIVE_JOB")
            for key,value in data.items():
                if key in ("title","problem","reference_solution") and (
                    not isinstance(value,str) or not value.strip()):
                    raise HTTPException(422,"EMPTY_TEXT_NOT_ALLOWED")
                if key=="fps" and (type(value)!=int or not 8<=value<=60):
                    raise HTTPException(422,"INVALID_FPS")
                if key=="voice" and value not in (
                    "zh-CN-YunxiNeural","zh-CN-XiaoxiaoNeural"):
                    raise HTTPException(422,"INVALID_VOICE")
            invalidates=any(k in data and getattr(l,k)!=data[k]
                            for k in ("problem","reference_solution","voice","fps"))
            for key,value in data.items():setattr(l,key,value)
            if invalidates:
                l.status="draft"
                # Old movie is historical and may be downloaded but not falsely
                # represented as verified for the newly edited source.
                l.latest_video=None;l.latest_manifest=None;l.session_path=None
            if invalidates:
                l.revision+=1
            db.commit();return describe_lesson(l)

    @api.post("/lessons/batch-delete")
    def lessons_batch_delete(data: DeleteBatch):
        ids=list(dict.fromkeys(data.ids))
        with SessionLocal() as db:
            rows=list(db.scalars(select(Lesson).where(
                Lesson.id.in_(ids),Lesson.deleted_at.is_(None)
            )))
            if len(rows)!=len(ids):raise HTTPException(404,"LESSON_BATCH_NOT_FOUND")
            active=db.scalars(select(Job).where(
                Job.lesson_id.in_(ids),Job.status.in_(("queued","running"))
            )).first()
            if active:raise HTTPException(409,"BATCH_HAS_ACTIVE_JOBS")
            for l in rows:l.deleted_at=now()
            db.commit();return {"deleted":ids,"count":len(ids)}

    @api.delete("/lessons/{id}")
    def lesson_delete(id: str):
        return lessons_batch_delete(DeleteBatch(ids=[id]))

    @api.get("/trash")
    def trash():
        with SessionLocal() as db:
            return [describe_lesson(l) for l in db.scalars(
                select(Lesson).where(Lesson.deleted_at.is_not(None))
            )]

    @api.post("/trash/restore")
    def trash_restore(data: DeleteBatch):
        with SessionLocal() as db:
            rows=list(db.scalars(select(Lesson).where(
                Lesson.id.in_(data.ids),Lesson.deleted_at.is_not(None)
            )))
            for l in rows:l.deleted_at=None
            db.commit();return {"restored":[l.id for l in rows]}

    @api.post("/lessons/{id}/package")
    async def upload_package(id: str,file: UploadFile=File(...)):
        with SessionLocal() as db:
            l=lesson_get(db,id)
            if l.status not in ("draft","package_needed"):
                raise HTTPException(409,"SOURCE_PACKAGE_ALREADY_SET")
            problem,reference=l.problem,l.reference_solution
        payload=await file.read(64*1024*1024+1)
        try:
            info=extract_engine_package(
                payload,lesson_root(id)/"package",
                problem=problem,reference_solution=reference,
            )
        except Exception as exc:
            raise HTTPException(422,str(exc)) from exc
        with SessionLocal() as db:
            l=lesson_get(db,id);l.status="script_pending"
            db.commit()
        return {"status":"script_pending",**info}

    @api.get("/lessons/{id}/script")
    def script(id: str):
        with SessionLocal() as db:
            l=lesson_get(db,id)
            if l.status not in ("script_pending","approved","ready"):
                raise HTTPException(409,"NO_ENGINE_PACKAGE")
        try:
            text=export_script(lesson_root(id)/"package")
        except Exception as exc:
            raise HTTPException(422,str(exc)) from exc
        return {"script":text,"status":"pending_review"}

    @api.post("/lessons/{id}/approve")
    def approve(id: str,data: Review):
        if not data.confirmed:raise HTTPException(422,"REVIEW_CONFIRMATION_REQUIRED")
        with SessionLocal() as db:
            l=lesson_get(db,id)
            if l.status not in ("script_pending","approved"):
                raise HTTPException(409,"NO_SCRIPT_TO_APPROVE")
        try:
            record=approve_script(lesson_root(id)/"package",data.reviewer)
        except Exception as exc:
            raise HTTPException(422,str(exc)) from exc
        with SessionLocal() as db:
            l=lesson_get(db,id);l.status="approved";db.commit()
        return {"status":"approved","reviewer":record["reviewer"],
                "source_sha256":record["source_spoken_sha256"]}

    @api.post("/lessons/{id}/render",status_code=202)
    def render(id: str):
        with SessionLocal() as db:
            l=lesson_get(db,id)
            if l.status!="approved":
                raise HTTPException(409,"SCRIPT_MUST_BE_APPROVED_OR_ALREADY_RENDERED")
            job=job_add(db,l,"render")
            response=describe_job(job)
        dispatch(job.id)
        return response

    @api.get("/jobs/{id}")
    def job_read(id: str):
        with SessionLocal() as db:
            job=db.get(Job,id)
            if job is None:raise HTTPException(404,"JOB_NOT_FOUND")
            return describe_job(job)

    @api.get("/jobs/{id}/events")
    def job_events(id: str):
        def messages():
            prev=None
            for _ in range(600):
                with SessionLocal() as db:
                    j=db.get(Job,id)
                    item=describe_job(j) if j else {"status":"missing"}
                current=json.dumps(item,ensure_ascii=False)
                if current!=prev:
                    yield f"data: {current}\n\n"
                    prev=current
                if item["status"] in ("succeeded","failed","cancelled","missing"):
                    return
                time.sleep(.4)
        return StreamingResponse(messages(),media_type="text/event-stream",
            headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

    @api.post("/jobs/{id}/cancel")
    def job_cancel(id:str):
        with SessionLocal() as db:
            job=db.get(Job,id)
            if not job:raise HTTPException(404,"JOB_NOT_FOUND")
            if job.status!="queued":
                raise HTTPException(409,"RUNNING_TASK_CANNOT_BE_FORCE_CANCELLED")
            job.status="cancelled";job.phase="已取消"
            db.commit();return describe_job(job)

    @api.get("/videos")
    def videos(q: str=""):
        with SessionLocal() as db:
            stmt=select(Lesson).where(
                Lesson.latest_video.is_not(None),Lesson.deleted_at.is_(None),
            )
            if q:stmt=stmt.where(Lesson.title.ilike(f"%{q}%"))
            return [describe_lesson(l) for l in db.scalars(
                stmt.order_by(Lesson.updated_at.desc())
            )]

    def video_path(db,id):
        l=lesson_get(db,id)
        if not l.latest_video:raise HTTPException(404,"VIDEO_NOT_READY")
        path=Path(l.latest_video).resolve()
        if not path.is_file() or not path.is_relative_to(lesson_root(id)):
            raise HTTPException(404,"VIDEO_MISSING")
        return l,path

    @api.get("/videos/{id}/stream")
    def stream_video(id: str):
        with SessionLocal() as db:
            l,path=video_path(db,id)
            return FileResponse(path,media_type="video/mp4")

    @api.get("/videos/{id}/download")
    def download_video(id: str):
        with SessionLocal() as db:
            l,path=video_path(db,id)
            return FileResponse(
                path,media_type="video/mp4",
                filename=f"{l.id}-latest.mp4",
            )

    @api.patch("/videos/{id}")
    def video_rename(id:str,data:Rename):
        return lesson_patch(id,{"title":data.title})

    @api.delete("/videos/{id}")
    def video_delete(id:str):
        return lesson_delete(id)

    @api.post("/videos/batch-delete")
    def videos_batch_delete(data:DeleteBatch):
        return lessons_batch_delete(data)

    @api.post("/videos/{id}/edits",status_code=202)
    def edit_submit(id: str,data: EditRequest):
        if edit_runner is None and not os.environ.get("WEIGUANG_EDIT_AI_CONFIG"):
            raise HTTPException(409,"EDIT_AI_CONFIGURATION_REQUIRED")
        with SessionLocal() as db:
            l=lesson_get(db,id)
            if not l.session_path:
                raise HTTPException(409,"VIDEO_SESSION_NOT_READY")
            row=EditRecord(lesson_id=id,original_instruction=data.instruction)
            db.add(row);db.commit();db.refresh(row)
            job=job_add(db,l,"edit",edit_id=row.id)
            result={"edit_id":row.id,"job":describe_job(job)}
        dispatch(job.id)
        return result

    @api.post("/videos/{id}/feedback")
    def video_feedback(id:str,data:Feedback):
        from animation_engine.iterative_edit_engine import record_feedback
        with SessionLocal() as db:
            l=lesson_get(db,id)
            if not l.session_path:raise HTTPException(409,"EDIT_SESSION_NOT_FOUND")
        try:
            result=record_feedback(
                Path(l.session_path),data.feedback,satisfied=data.satisfied,
            )
        except Exception as exc:
            raise HTTPException(409,str(exc)) from exc
        with SessionLocal() as db:
            row=db.scalars(select(EditRecord).where(
                EditRecord.lesson_id==id,EditRecord.status=="preview_ready"
            ).order_by(EditRecord.created_at.desc())).first()
            if row:
                row.feedback=data.feedback
                row.satisfied=int(data.satisfied)
                row.status="accepted" if data.satisfied else "needs_revision"
                db.commit()
        return result

    @api.get("/system/edit-history/export")
    def export_all_edit_history():
        from animation_engine.iterative_edit_engine import export_history
        with SessionLocal() as db:
            lessons_all=list(db.scalars(select(Lesson)))
            api_history=list(db.scalars(select(EditRecord)))
        engine_history=[]
        for l in lessons_all:
            if not l.session_path or not Path(l.session_path).exists():
                continue
            with tempfile.TemporaryDirectory(prefix="wg-export-") as tmp:
                try:
                    data=export_history(Path(l.session_path),Path(tmp)/"records.json")
                except Exception:
                    data={"error":"SESSION_EXPORT_UNAVAILABLE","rounds":[]}
                engine_history.append({"lesson_id":l.id,"session":data})
        all_data={
            "schema_version":"1.0","mode":"weiguang_all_edit_history",
            "exported_at":datetime.now(timezone.utc).isoformat(),
            "sessions":engine_history,
            "api_attempts":[{
                "id":x.id,"lesson_id":x.lesson_id,
                "original_instruction":x.original_instruction,
                "status":x.status,"error":x.error,
                "feedback":x.feedback,"satisfied":bool(x.satisfied),
            } for x in api_history],
            "media_embedded":False,
        }
        text=json.dumps(all_data,ensure_ascii=False,indent=2)+"\n"
        return StreamingResponse(
            iter([text.encode("utf-8")]),media_type="application/json",
            headers={"Content-Disposition":
                     'attachment; filename="weiguang_all_edit_history.json"'},
        )

    @api.get("/settings")
    def settings():
        return {"default_fps":60,"default_resolution":"1280x720",
                "voices":["zh-CN-YunxiNeural","zh-CN-XiaoxiaoNeural"],
                "max_render_jobs":1,
                "ai_configured":bool(os.environ.get("WEIGUANG_EDIT_AI_CONFIG"))}

    app.include_router(api)
    from fastapi.staticfiles import StaticFiles
    frontend = Path(__file__).resolve().parents[3] / "frontend"
    if frontend.is_dir() and (frontend / "index.html").exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="web")
    return app


app=create_app()


def run():
    import uvicorn
    uvicorn.run(
        "weiguang_backend.main:app",host="127.0.0.1",
        port=int(os.environ.get("WEIGUANG_PORT","8000")),
    )
