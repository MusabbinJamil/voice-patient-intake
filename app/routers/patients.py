"""REST API for patient records.

Endpoints (all responses use the {data, error} envelope):
    GET    /patients            list + optional ?last_name= ?date_of_birth= ?phone_number=
    GET    /patients/{id}       fetch one by UUID
    POST   /patients            create (201)
    PUT    /patients/{id}       partial update
    DELETE /patients/{id}       soft delete (sets deleted_at)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from .. import crud
from ..db import get_db
from ..responses import envelope, error_body
from ..schemas import PatientCreate, PatientOut, PatientUpdate

logger = logging.getLogger("app.api")
router = APIRouter(prefix="/patients", tags=["patients"])


def _out(patient) -> dict:
    return PatientOut.model_validate(patient).model_dump()


@router.get("")
def list_patients(
    last_name: Optional[str] = None,
    date_of_birth: Optional[str] = None,
    phone_number: Optional[str] = None,
    db: Session = Depends(get_db),
):
    patients = crud.list_patients(
        db,
        last_name=last_name,
        date_of_birth=date_of_birth,
        phone_number=phone_number,
    )
    return envelope([_out(p) for p in patients])


@router.get("/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if patient is None:
        return envelope(error=error_body(404, "Patient not found"), status_code=404)
    return envelope(_out(patient))


@router.post("")
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)):
    patient = crud.create_patient(db, payload.model_dump())
    # Observability: log the final persisted payload to stdout.
    logger.info("PATIENT_CREATED %s", jsonable_encoder(_out(patient)))
    return envelope(_out(patient), status_code=201)


@router.put("/{patient_id}")
def update_patient(
    patient_id: str, payload: PatientUpdate, db: Session = Depends(get_db)
):
    patient = crud.get_patient(db, patient_id)
    if patient is None:
        return envelope(error=error_body(404, "Patient not found"), status_code=404)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return envelope(
            error=error_body(422, "No valid fields supplied for update"),
            status_code=422,
        )
    patient = crud.update_patient(db, patient, changes)
    logger.info("PATIENT_UPDATED %s fields=%s", patient.patient_id, list(changes))
    return envelope(_out(patient))


@router.delete("/{patient_id}")
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if patient is None:
        return envelope(error=error_body(404, "Patient not found"), status_code=404)
    crud.soft_delete(db, patient)
    logger.info("PATIENT_SOFT_DELETED %s", patient.patient_id)
    return envelope({"patient_id": str(patient.patient_id), "deleted": True})
