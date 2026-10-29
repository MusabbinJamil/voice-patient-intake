"""Voice-agent integration endpoint (Vapi server webhook).

A single endpoint handles every message Vapi sends:
  * `tool-calls`         -> run a tool and return results
  * `end-of-call-report` -> persist the transcript + summary (observability)
  * anything else        -> acknowledged with 200

Tools (real-time / incremental design):
  * lookup_patient_by_phone  -> returning-caller detection
  * save_patient_progress    -> validate + persist each field AS IT ARRIVES
                                (a draft row keyed to the Vapi call id); returns
                                what's still missing, or a field-specific error
                                so the agent re-prompts immediately.
  * finalize_registration    -> after the caller confirms, mark the draft
                                'registered'. Fails if any required field is
                                missing/invalid, so the agent can never claim a
                                save that didn't happen.
  * update_patient           -> update an existing registered patient.

Everything is validated with the SAME Pydantic rules as the REST API, so the
agent can never write data that would fail server-side validation.
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
from ..schemas import PatientUpdate
from ..validators import validate_phone

logger = logging.getLogger("app.vapi")
router = APIRouter(prefix="/vapi", tags=["vapi"])

# Fields the agent may send; everything else in the args is ignored.
_WRITABLE = set(PatientUpdate.model_fields.keys())


def _format_validation_error(exc: ValidationError) -> str:
    problems = "; ".join(f"{err['loc'][-1]} {err['msg']}" for err in exc.errors())
    return (
        "VALIDATION_ERROR — not saved. Problems: "
        f"{problems}. Politely ask the caller to correct the field(s) above, then "
        "call this tool again with the corrected value."
    )


def _clean(args: dict) -> dict:
    return {k: v for k, v in args.items() if k in _WRITABLE and v not in (None, "")}


# --- Tool handlers (return a string the LLM relays to the caller) ---

def _tool_lookup(db: Session, args: dict, call_id: str) -> str:
    try:
        norm = validate_phone(args.get("phone_number", ""))
    except ValueError:
        return "The phone number given is not a valid US number; ask the caller to repeat it."
    existing = crud.get_by_phone(db, norm)
    if existing:
        return (
            f"FOUND — an existing record belongs to {existing.first_name} "
            f"{existing.last_name} (patient_id {existing.patient_id}). Tell the caller "
            "we already have a record and ask if they'd like to update it instead of "
            "creating a new one (if yes, use update_patient)."
        )
    return "NOT_FOUND — no existing patient for that number. Proceed to collect their details."


def _tool_save_progress(db: Session, args: dict, call_id: str) -> str:
    if not call_id:
        return "SYSTEM_ERROR — missing call context; cannot save progress right now."
    if args.get("start_over") is True:
        crud.reset_draft(db, call_id)
        return "RESET — cleared everything. Start again by asking for the first name."

    fields = _clean(args)
    if not fields:
        return "Nothing to save yet; ask the caller for the next piece of information."
    try:
        validated = PatientUpdate(**fields).model_dump(exclude_unset=True)
    except ValidationError as exc:
        return _format_validation_error(exc)

    patient = crud.upsert_draft(db, call_id, validated)
    saved = ", ".join(validated.keys())
    missing = crud.missing_required(patient)
    logger.info("DRAFT_SAVED call=%s fields=[%s] missing=%s", call_id, saved, missing)
    if missing:
        return f"SAVED ({saved}). Still required: {', '.join(missing)}. Ask for the next one."
    return (
        f"SAVED ({saved}). All required fields are collected. Offer optional info "
        "(insurance, emergency contact, preferred language), then read EVERYTHING "
        "back, get the caller's confirmation, and call finalize_registration."
    )


def _tool_finalize(db: Session, args: dict, call_id: str) -> str:
    patient = crud.get_draft_by_call_id(db, call_id)

    # Allow any last-minute fields to be passed straight into finalize.
    extra = _clean(args)
    if extra:
        try:
            validated = PatientUpdate(**extra).model_dump(exclude_unset=True)
        except ValidationError as exc:
            return _format_validation_error(exc)
        patient = crud.upsert_draft(db, call_id, validated)

    if patient is None:
        return "NO_DATA — nothing has been captured for this call. Collect the details first."

    missing = crud.missing_required(patient)
    if missing:
        return (
            f"INCOMPLETE — cannot register yet. Still missing: {', '.join(missing)}. "
            "Collect these, then call finalize_registration again. Do NOT tell the "
            "caller they are registered."
        )

    existing = crud.get_by_phone(db, patient.phone_number)
    if existing and existing.patient_id != patient.patient_id:
        return (
            f"DUPLICATE — {existing.first_name} {existing.last_name} is already "
            f"registered with this phone (patient_id {existing.patient_id}). Offer to "
            "update that record with update_patient instead of creating a new one."
        )

    try:
        crud.finalize(db, patient)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Finalize DB write failed")
        return "SAVE_FAILED — a system error prevented registration. Apologize; do not claim success."
    logger.info("PATIENT_REGISTERED via voice patient_id=%s", patient.patient_id)
    return (
        f"SUCCESS — registered (patient_id {patient.patient_id}). Confirm to the caller "
        f"that they are all set, {patient.first_name}, then end the call gracefully."
    )


def _tool_update(db: Session, args: dict, call_id: str) -> str:
    patient = crud.get_patient(db, args.get("patient_id"))
    if patient is None:
        return "NOT_FOUND — no patient with that id; do not claim the update succeeded."
    fields = _clean(args)
    if not fields:
        return "No changes supplied; ask the caller what they'd like to update."
    try:
        validated = PatientUpdate(**fields).model_dump(exclude_unset=True)
    except ValidationError as exc:
        return _format_validation_error(exc)
    crud.update_patient(db, patient, validated)
    logger.info("PATIENT_UPDATED via voice patient_id=%s", patient.patient_id)
    return f"SUCCESS — record updated for {patient.first_name} {patient.last_name}."


_TOOLS = {
    "lookup_patient_by_phone": _tool_lookup,
    "save_patient_progress": _tool_save_progress,
    "finalize_registration": _tool_finalize,
    "update_patient": _tool_update,
}


def _dispatch(name: str, args: dict, db: Session, call_id: str) -> str:
    handler = _TOOLS.get(name)
    if handler is None:
        logger.warning("Unknown tool requested: %s", name)
        return f"ERROR — unknown tool '{name}'."
    return handler(db, args, call_id)


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
    if settings.vapi_shared_secret and x_vapi_secret != settings.vapi_shared_secret:
        logger.warning("Rejected Vapi webhook with bad/missing secret")
        return {"error": "unauthorized"}

    body = await request.json()
    message = body.get("message", {}) or {}
    mtype = message.get("type")
    call_id = (message.get("call") or {}).get("id")

    # --- Tool calls (modern "tool-calls" and legacy "function-call") ---
    if mtype in ("tool-calls", "function-call"):
        tool_calls = message.get("toolCalls") or message.get("toolCallList") or []
        if not tool_calls and message.get("functionCall"):
            fc = message["functionCall"]
            result = _dispatch(fc.get("name"), _parse_args(fc.get("parameters")), db, call_id)
            return {"result": result}

        results = []
        for call in tool_calls:
            fn = call.get("function", {}) or {}
            name = fn.get("name")
            args = _parse_args(fn.get("arguments"))
            cid = call.get("id") or call.get("toolCallId")
            results.append({"toolCallId": cid, "result": _dispatch(name, args, db, call_id)})
        return {"results": results}

    # --- End-of-call report: persist transcript + summary ---
    if mtype == "end-of-call-report":
        artifact = message.get("artifact") or {}
        analysis = message.get("analysis") or {}
        call = message.get("call") or {}
        customer = message.get("customer") or {}
        crud.create_call_log(
            db,
            call_id=call.get("id"),
            phone_number=customer.get("number"),
            transcript=message.get("transcript") or artifact.get("transcript"),
            summary=message.get("summary") or analysis.get("summary"),
            final_payload=analysis or None,
        )
        logger.info("CALL_ENDED call_id=%s", call.get("id"))
        return {"ok": True}

    return {"ok": True}
