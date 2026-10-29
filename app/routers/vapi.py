"""Voice-agent integration endpoint (Vapi server webhook).

A single endpoint handles every message Vapi sends to the server:
  * `tool-calls`        -> run a tool (lookup / register / update) and return results
  * `end-of-call-report`-> persist the transcript + summary for observability
  * anything else       -> acknowledged with 200

The tools call the SAME validation + data layer as the REST API, so the agent
can never write data that would fail server-side validation. Validation
failures are returned to the agent as plain-language strings so it can
re-prompt the caller for the specific bad field.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from .. import crud
from ..config import settings
from ..db import get_db
from ..schemas import PatientCreate, PatientUpdate
from ..validators import validate_phone

logger = logging.getLogger("app.vapi")
router = APIRouter(prefix="/vapi", tags=["vapi"])


def _format_validation_error(exc: ValidationError) -> str:
    problems = "; ".join(
        f"{err['loc'][-1]} {err['msg']}" for err in exc.errors()
    )
    return (
        "VALIDATION_ERROR — the record was not saved. Problems: "
        f"{problems}. Politely ask the caller to correct the field(s) above, "
        "then try again."
    )


# --- Individual tool handlers (return a string the LLM relays to the caller) ---

def _tool_lookup(db: Session, args: dict) -> str:
    phone = args.get("phone_number", "")
    try:
        norm = validate_phone(phone)
    except ValueError:
        return "The phone number given is not a valid US number; ask the caller to repeat it."
    existing = crud.get_by_phone(db, norm)
    if existing:
        return (
            f"FOUND — an existing record belongs to {existing.first_name} "
            f"{existing.last_name} (patient_id {existing.patient_id}). Tell the caller "
            "we already have a record and ask if they would like to update it instead "
            "of creating a new one."
        )
    return "NOT_FOUND — no existing patient for that number. Proceed to collect their details."


def _tool_register(db: Session, args: dict) -> str:
    try:
        data = PatientCreate(**args)
    except ValidationError as exc:
        return _format_validation_error(exc)

    existing = crud.get_by_phone(db, data.phone_number)
    if existing:
        return (
            f"DUPLICATE — {existing.first_name} {existing.last_name} already has a record "
            f"(patient_id {existing.patient_id}) for this phone number. Ask the caller if "
            "they want to update the existing record instead; if yes, call update_patient."
        )
    try:
        patient = crud.create_patient(db, data.model_dump())
    except Exception:  # pragma: no cover - defensive: DB write failure
        logger.exception("Voice register DB write failed")
        return (
            "SAVE_FAILED — a system error prevented saving. Apologize to the caller and "
            "say we could not save the record right now."
        )
    logger.info("PATIENT_CREATED via voice patient_id=%s", patient.patient_id)
    return (
        f"SUCCESS — patient saved with patient_id {patient.patient_id}. "
        f"Confirm to the caller that they are all set, {patient.first_name}."
    )


def _tool_update(db: Session, args: dict) -> str:
    patient = crud.get_patient(db, args.get("patient_id"))
    if patient is None:
        return "NOT_FOUND — no patient with that id; do not claim the update succeeded."
    fields = {
        k: val for k, val in args.items() if k != "patient_id" and val is not None
    }
    try:
        data = PatientUpdate(**fields)
    except ValidationError as exc:
        return _format_validation_error(exc)
    crud.update_patient(db, patient, data.model_dump(exclude_unset=True))
    logger.info("PATIENT_UPDATED via voice patient_id=%s", patient.patient_id)
    return f"SUCCESS — record updated for {patient.first_name} {patient.last_name}."


_TOOLS = {
    "lookup_patient_by_phone": _tool_lookup,
    "register_patient": _tool_register,
    "update_patient": _tool_update,
}


def _dispatch(name: str, args: dict, db: Session) -> str:
    handler = _TOOLS.get(name)
    if handler is None:
        logger.warning("Unknown tool requested: %s", name)
        return f"ERROR — unknown tool '{name}'."
    return handler(db, args)


def _parse_args(raw) -> dict:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return raw or {}


@router.post("/webhook")
async def vapi_webhook(
    request: Request,
    x_vapi_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    # Authenticate Vapi via the shared secret header (skipped if unset locally).
    if settings.vapi_shared_secret and x_vapi_secret != settings.vapi_shared_secret:
        logger.warning("Rejected Vapi webhook with bad/missing secret")
        return {"error": "unauthorized"}

    body = await request.json()
    message = body.get("message", {}) or {}
    mtype = message.get("type")

    # --- Tool calls (modern "tool-calls" and legacy "function-call") ---
    if mtype in ("tool-calls", "function-call"):
        tool_calls = message.get("toolCalls") or message.get("toolCallList") or []
        if not tool_calls and message.get("functionCall"):
            # Legacy single-function shape.
            fc = message["functionCall"]
            result = _dispatch(fc.get("name"), _parse_args(fc.get("parameters")), db)
            return {"result": result}

        results = []
        for call in tool_calls:
            fn = call.get("function", {}) or {}
            name = fn.get("name")
            args = _parse_args(fn.get("arguments"))
            call_id = call.get("id") or call.get("toolCallId")
            results.append({"toolCallId": call_id, "result": _dispatch(name, args, db)})
        return {"results": results}

    # --- End-of-call report: persist transcript + summary (observability) ---
    if mtype == "end-of-call-report":
        artifact = message.get("artifact") or {}
        analysis = message.get("analysis") or {}
        call = message.get("call") or {}
        customer = message.get("customer") or {}
        transcript = message.get("transcript") or artifact.get("transcript")
        summary = message.get("summary") or analysis.get("summary")
        crud.create_call_log(
            db,
            call_id=call.get("id"),
            phone_number=customer.get("number"),
            transcript=transcript,
            summary=summary,
            final_payload=analysis or None,
        )
        logger.info("CALL_ENDED call_id=%s summary=%s", call.get("id"), summary)
        return {"ok": True}

    # Status updates, speech events, etc. — just acknowledge.
    return {"ok": True}
