"""Every backend API integration test uses a distinct real PostgreSQL schema."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import close_all_sessions

from pg_test_db import isolated_test_database


@pytest.fixture(autouse=True)
def postgres_only_test_backend(monkeypatch):
    with isolated_test_database() as database_url:
        monkeypatch.setenv("DATABASE_URL",database_url)
        try:
            yield
        finally:
            close_all_sessions()
