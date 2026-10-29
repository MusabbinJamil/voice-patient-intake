"""SQLAlchemy ORM models — the persistent schema.

Design notes:
* `patient_id` is a UUID primary key (portable across Postgres/SQLite).
* Records are captured **incrementally**: the voice agent persists each field as
  it is collected, so a row can be a partial `draft` before it becomes
  `registered`. Required columns are therefore nullable at the column level, but
  a CHECK constraint guarantees that any row with status='registered' has every
  required field populated — so completeness is still enforced by the database.
* `sex` is stored as text with a CHECK constraint (portable, exact values).
* Deletes are *soft*: `deleted_at` is stamped and the row is kept.
* `created_at` / `updated_at` are DB-maintained in UTC.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

SEX_VALUES = ("Male", "Female", "Other", "Decline to Answer")
REQUIRED_FIELDS = (
    "first_name",
    "last_name",
    "date_of_birth",
    "sex",
    "phone_number",
    "address_line_1",
    "city",
    "state",
    "zip_code",
)

_REGISTERED_COMPLETE = (
    "status <> 'registered' OR ("
    + " AND ".join(f"{c} IS NOT NULL" for c in REQUIRED_FIELDS)
    + ")"
)


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        CheckConstraint(
            "sex IS NULL OR sex IN ('Male','Female','Other','Decline to Answer')",
            name="ck_patients_sex",
        ),
        CheckConstraint("status IN ('draft','registered')", name="ck_patients_status"),
        CheckConstraint(_REGISTERED_COMPLETE, name="ck_patients_registered_complete"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )

    # Lifecycle: 'draft' while being collected, 'registered' once confirmed.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # Links an in-progress draft to the Vapi call that is filling it.
    call_id: Mapped[str | None] = mapped_column(String(100), index=True)

    # --- Required demographics (nullable to allow incremental drafts) ---
    first_name: Mapped[str | None] = mapped_column(String(50))
    last_name: Mapped[str | None] = mapped_column(String(50))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    sex: Mapped[str | None] = mapped_column(String(20))
    phone_number: Mapped[str | None] = mapped_column(String(10), index=True)
    address_line_1: Mapped[str | None] = mapped_column(String(255))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    zip_code: Mapped[str | None] = mapped_column(String(10))

    # --- Optional demographics ---
    email: Mapped[str | None] = mapped_column(String(255))
    address_line_2: Mapped[str | None] = mapped_column(String(255))
    insurance_provider: Mapped[str | None] = mapped_column(String(255))
    insurance_member_id: Mapped[str | None] = mapped_column(String(100))
    preferred_language: Mapped[str] = mapped_column(
        String(50), default="English", server_default="English"
    )
    emergency_contact_name: Mapped[str | None] = mapped_column(String(255))
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(10))

    # --- System-managed ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class CallLog(Base):
    """One row per completed call (Vapi end-of-call report): transcript + summary
    for observability and the optional transcript bonus."""

    __tablename__ = "call_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    call_id: Mapped[str | None] = mapped_column(String(100), index=True)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("patients.patient_id"), nullable=True
    )
    phone_number: Mapped[str | None] = mapped_column(String(20))
    transcript: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    final_payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
