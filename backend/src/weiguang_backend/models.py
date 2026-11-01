"""Persistent metadata only: large artifacts stay in per-lesson directories."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)


def uid():
    return uuid4().hex


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    project_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(180))
    problem: Mapped[str] = mapped_column(Text)
    reference_solution: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    voice: Mapped[str] = mapped_column(String(80), default="zh-CN-YunxiNeural")
    fps: Mapped[int] = mapped_column(Integer, default=60)
    latest_video: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_manifest: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    lesson_id: Mapped[str] = mapped_column(String(32), ForeignKey("lessons.id"))
    edit_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(24), default="render")
    status: Mapped[str] = mapped_column(String(24), default="queued")
    phase: Mapped[str] = mapped_column(String(80), default="排队")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class EditRecord(Base):
    __tablename__ = "edit_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    lesson_id: Mapped[str] = mapped_column(String(32), ForeignKey("lessons.id"))
    original_instruction: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    satisfied: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EditSessionArchive(Base):
    """Immutable session index, retained when a lesson's source is replaced."""
    __tablename__ = "edit_session_archives"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    lesson_id: Mapped[str] = mapped_column(String(32), ForeignKey("lessons.id"))
    job_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    session_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
