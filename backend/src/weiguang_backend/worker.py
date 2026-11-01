"""Celery runner; each job reloads committed DB metadata after worker restart."""
import os

from celery import Celery

celery_app=Celery(
    "weiguang",
    broker=os.environ.get("CELERY_BROKER_URL","redis://localhost:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND","redis://localhost:6379/1"),
)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=3600,
    task_time_limit=3900,
)


@celery_app.task(name="weiguang.run_job",bind=True)
def execute(self,job_id: str):
    from .main import app
    app.state.run_job(job_id)
