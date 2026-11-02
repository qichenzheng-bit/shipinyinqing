"""PostgreSQL-only contract and real persistence on the Windows API path."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from weiguang_backend.database import postgres_url
from weiguang_backend.main import create_app
from weiguang_backend.models import Lesson, Project


@pytest.mark.parametrize("raw",[
    "sqlite:///C:/broken/lesson.db",
    "sqlite+pysqlite:///:memory:",
    "mysql+pymysql://user:pass@localhost/weiguang",
    "duckdb:///weiguang.duckdb",
])
def test_refuse_any_non_postgresql_backend_without_creating_files(raw,tmp_path):
    root=tmp_path/"never-create"
    with pytest.raises(ValueError,match="POSTGRESQL_ONLY_DATABASE_BACKEND"):
        create_app(data_dir=root,database_url=raw,local_dev=True)
    assert not root.exists()


def test_no_implicit_file_database_even_in_local_dev(tmp_path,monkeypatch):
    monkeypatch.delenv("DATABASE_URL",raising=False)
    root=tmp_path/"never-create"
    with pytest.raises(RuntimeError,match="POSTGRESQL_DATABASE_URL_REQUIRED"):
        create_app(data_dir=root,local_dev=True)
    assert not root.exists()
    assert not list(tmp_path.rglob("*.db"))


def test_postgres_driver_normalization_without_psycopg2():
    url=postgres_url("postgresql://user:pass@localhost:5432/weiguang")
    assert url.drivername=="postgresql+psycopg"
    assert url.database=="weiguang"
    assert url.host=="localhost"


def test_postgresql_tables_real_write_read_and_restart(tmp_path):
    root=tmp_path/"lesson-media"
    app=create_app(data_dir=root,local_dev=True,eager=True)
    assert app.state.db_engine.dialect.name=="postgresql"
    with app.state.db_engine.connect() as conn:
        assert conn.execute(text("select current_schema()")).scalar_one().startswith("wgtest_")
        assert conn.execute(text("select current_setting('server_version_num')")).scalar_one()
    client=TestClient(app)
    project=client.post("/api/v1/projects",json={"title":"PostgreSQL 练习"}).json()
    r=client.post("/api/v1/lessons",json={
        "project_id":project["id"],"title":"微分公式",
        "problem":"计算 2+3","reference_solution":"5",
    })
    assert r.status_code==201,r.text
    key=r.json()["id"]
    app.state.db_engine.dispose()
    # A second app instance must read data from Postgres, not a local file.
    reopened=create_app(data_dir=root,local_dev=True,eager=True)
    with reopened.state.SessionLocal() as db:
        item=db.get(Lesson,key)
        assert item is not None and item.project_id==project["id"]
        assert db.get(Project,project["id"]).title=="PostgreSQL 练习"
    reopened.state.db_engine.dispose()
    assert not list(root.rglob("*.db"))
