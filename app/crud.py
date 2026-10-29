"""Data-access layer. The REST routes and the voice-agent tools both call
these functions, so persistence logic lives in exactly one place.

Two write paths:
  * REST `POST /patients` -> `create_patient` (atomic, status='registered').
  * Voice agent -> `upsert_draft` (incremental, status='draft') per field, then
    `finalize` (status='registered') once confirmed and complete.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .models import REQUIRED_FIELDS
from .validators import normalize_phone, parse_dob


def get_patient(
    db: Session, patient_id, include_deleted: bool = False
) -> Optional[models.Patient]:
    try:
        pid = uuid.UUID(str(patient_id))
    except (ValueError, TypeError, AttributeError):
        return None
    patient = db.get(models.Patient, pid)
    if patient and patient.deleted_at is not None and not include_deleted:
        return None
    return patient


def get_by_phone(db: Session, phone: str) -> Optional[models.Patient]:
    """Find a *registered* patient by phone (used for duplicate detection)."""
    norm = normalize_phone(phone)
    stmt = select(models.Patient).where(
        models.Patient.phone_number == norm,
        models.Patient.status == "registered",
        models.Patient.deleted_at.is_(None),
    )
    return db.scalars(stmt).first()


def get_draft_by_call_id(db: Session, call_id: str) -> Optional[models.Patient]:
    if not call_id:
        return None
    stmt = (
        select(models.Patient)
        .where(
            models.Patient.call_id == call_id,
            models.Patient.status == "draft",
            models.Patient.deleted_at.is_(None),
        )
        .order_by(models.Patient.created_at.desc())
    )
    return db.scalars(stmt).first()


def list_patients(
    db: Session,
    last_name: Optional[str] = None,
    date_of_birth: Optional[str] = None,
    phone_number: Optional[str] = None,
    status: Optional[str] = "registered",
    include_deleted: bool = False,
) -> list[models.Patient]:
    stmt = select(models.Patient)
    if not include_deleted:
        stmt = stmt.where(models.Patient.deleted_at.is_(None))
    if status:  # None -> all statuses (registered + draft)
        stmt = stmt.where(models.Patient.status == status)
    if last_name:
        stmt = stmt.where(func.lower(models.Patient.last_name) == last_name.strip().lower())
    if phone_number:
        stmt = stmt.where(models.Patient.phone_number == normalize_phone(phone_number))
    if date_of_birth:
        try:
            stmt = stmt.where(models.Patient.date_of_birth == parse_dob(date_of_birth))
        except ValueError:
            return []
    stmt = stmt.order_by(models.Patient.created_at.desc())
    return list(db.scalars(stmt).all())


def missing_required(patient: models.Patient) -> list[str]:
    """Required fields that are not yet populated on this record."""
    return [f for f in REQUIRED_FIELDS if getattr(patient, f) in (None, "")]


def create_patient(db: Session, data: dict) -> models.Patient:
    """Atomic create via the REST API — a fully-registered patient."""
    data = {**data, "status": "registered"}
    patient = models.Patient(**data)
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def upsert_draft(db: Session, call_id: str, fields: dict) -> models.Patient:
    """Create or update the draft tied to this call, persisting each field as it
    arrives (real-time storage)."""
    patient = get_draft_by_call_id(db, call_id)
    if patient is None:
        patient = models.Patient(call_id=call_id, status="draft", **fields)
        db.add(patient)
    else:
        for key, value in fields.items():
            setattr(patient, key, value)
    db.commit()
    db.refresh(patient)
    return patient


def reset_draft(db: Session, call_id: str) -> None:
    """Start-over: soft-delete any in-progress draft for this call."""
    patient = get_draft_by_call_id(db, call_id)
    if patient is not None:
        patient.deleted_at = func.now()
        db.commit()


def finalize(db: Session, patient: models.Patient) -> models.Patient:
    patient.status = "registered"
    db.commit()
    db.refresh(patient)
    return patient


def update_patient(db: Session, patient: models.Patient, data: dict) -> models.Patient:
    for key, value in data.items():
        setattr(patient, key, value)
    db.commit()
    db.refresh(patient)
    return patient


def soft_delete(db: Session, patient: models.Patient) -> models.Patient:
    patient.deleted_at = func.now()
    db.commit()
    db.refresh(patient)
    return patient


def create_call_log(
    db: Session,
    call_id: Optional[str] = None,
    phone_number: Optional[str] = None,
    transcript: Optional[str] = None,
    summary: Optional[str] = None,
    final_payload: Optional[dict] = None,
) -> models.CallLog:
    patient = get_by_phone(db, phone_number) if phone_number else None
    log = models.CallLog(
        call_id=call_id,
        phone_number=phone_number,
        transcript=transcript,
        summary=summary,
        final_payload=final_payload,
        patient_id=patient.patient_id if patient else None,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def recent_call_logs(db: Session, limit: int = 10) -> list[models.CallLog]:
    stmt = select(models.CallLog).order_by(models.CallLog.created_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())
