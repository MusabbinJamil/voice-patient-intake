"""Database engine and session management.

Works against either Postgres (production, via Neon) or SQLite (local dev).
The connection string is normalized so the psycopg v3 driver is used for
Postgres regardless of the scheme Neon hands us.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import settings


def _normalize_url(url: str) -> str:
    """Force the psycopg (v3) driver for Postgres URLs."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _normalize_url(settings.database_url)

connect_args: dict = {}
engine_kwargs: dict = {"pool_pre_ping": True, "future": True}

if DATABASE_URL.startswith("sqlite"):
    # Needed because FastAPI may touch the session from different threads.
    connect_args = {"check_same_thread": False}
else:
    # Recycle connections so Neon's scale-to-zero doesn't hand us dead sockets.
    engine_kwargs["pool_recycle"] = 300

engine = create_engine(DATABASE_URL, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
