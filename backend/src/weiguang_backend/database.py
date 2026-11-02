"""PostgreSQL 17 is the ONLY supported metadata database.

The Windows app launches Docker Desktop/WSL2 with a persistent PostgreSQL
volume. Never create an implicit local file database or log credentials.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url


def postgres_url(raw: str | URL | None) -> URL:
    if not raw:
        raise RuntimeError(
            "POSTGRESQL_DATABASE_URL_REQUIRED: configure PostgreSQL in DATABASE_URL"
        )
    try:
        parsed = make_url(raw) if isinstance(raw, str) else raw
    except Exception as exc:
        raise ValueError("POSTGRESQL_DATABASE_URL_INVALID") from exc
    if parsed.drivername not in ("postgresql", "postgresql+psycopg"):
        raise ValueError("POSTGRESQL_ONLY_DATABASE_BACKEND")
    if not parsed.database or not parsed.host or not parsed.username:
        raise ValueError("POSTGRESQL_CONNECTION_DETAILS_REQUIRED")
    # Do not depend on an implicit psycopg2 driver (which is not installed).
    return parsed.set(drivername="postgresql+psycopg")


def postgres_engine(raw: str | URL | None):
    url = postgres_url(raw)
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)
