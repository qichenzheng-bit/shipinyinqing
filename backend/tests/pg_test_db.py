"""Ephemeral PostgreSQL *schemas* isolate CI tests without SQLite.

Uses a dedicated TEST URL. Every test gets a unique schema within an existing
Postgres 17 database; does not create, truncate or delete user databases.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from weiguang_backend.database import postgres_url


@contextmanager
def isolated_test_database():
    admin_url=os.environ.get("WEIGUANG_TEST_POSTGRES_ADMIN_URL")
    if not admin_url:
        raise RuntimeError(
            "WEIGUANG_TEST_POSTGRES_ADMIN_URL_REQUIRED: real PostgreSQL tests "
            "must have a dedicated CI-only PostgreSQL server"
        )
    url=postgres_url(admin_url)
    # Never use a production-like DB name for the CI test schema.
    if url.database != "postgres":
        raise RuntimeError("TEST_POSTGRES_ADMIN_DATABASE_MUST_BE_postgres")
    if url.host not in ("127.0.0.1", "localhost", "::1"):
        raise RuntimeError("TEST_POSTGRES_MUST_BE_LOCAL_LOOPBACK")
    schema="wgtest_"+uuid4().hex
    admin=create_engine(url,pool_pre_ping=True)
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        params=dict(url.query)
        if "options" in params:
            raise RuntimeError("TEST_POSTGRES_ADMIN_OPTIONS_NOT_ALLOWED")
        params["options"]="-csearch_path="+schema
        isolated=url.set(query=params).render_as_string(hide_password=False)
        try:
            yield isolated
        finally:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    finally:
        admin.dispose()
