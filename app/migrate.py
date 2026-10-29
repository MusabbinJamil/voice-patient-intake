"""Tiny, idempotent schema evolution for the incremental-draft columns.

`create_all()` only creates missing tables; it never alters an existing one. The
already-deployed Postgres table was created with the old (all-NOT-NULL, no
status/call_id) schema, so this brings it up to the current model **without
dropping data** (the seed rows and any registrations survive — persistence
requirement). On a fresh database every statement is a harmless no-op.

Each statement runs in its own transaction so an "already exists" error on one
(e.g. a CHECK constraint that's already present) never aborts the others.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .models import REQUIRED_FIELDS, _REGISTERED_COMPLETE

logger = logging.getLogger("app.migrate")


def ensure_schema(engine: Engine) -> None:
    # SQLite (local dev/tests) always gets the current schema from create_all().
    if engine.dialect.name != "postgresql":
        return

    statements: list[str] = [
        "ALTER TABLE patients ADD COLUMN IF NOT EXISTS status varchar(20)",
        "ALTER TABLE patients ADD COLUMN IF NOT EXISTS call_id varchar(100)",
        # Existing rows predate drafts, so they are complete -> registered.
        "UPDATE patients SET status='registered' WHERE status IS NULL",
        "ALTER TABLE patients ALTER COLUMN status SET DEFAULT 'draft'",
        "ALTER TABLE patients ALTER COLUMN status SET NOT NULL",
        "CREATE INDEX IF NOT EXISTS ix_patients_call_id ON patients (call_id)",
    ]
    # Relax NOT NULL on required columns so drafts can be partial.
    statements += [
        f"ALTER TABLE patients ALTER COLUMN {col} DROP NOT NULL"
        for col in REQUIRED_FIELDS
    ]
    # Add the new CHECK constraints (ignored if already present).
    statements += [
        "ALTER TABLE patients ADD CONSTRAINT ck_patients_status "
        "CHECK (status IN ('draft','registered'))",
        "ALTER TABLE patients ADD CONSTRAINT ck_patients_registered_complete "
        f"CHECK ({_REGISTERED_COMPLETE})",
    ]

    for stmt in statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception as exc:  # noqa: BLE001 - tolerate already-applied steps
            logger.debug("skip migration step (%s): %s", stmt.split()[:4], exc)
    logger.info("Schema evolution check complete")
