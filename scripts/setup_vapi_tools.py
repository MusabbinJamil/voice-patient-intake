#!/usr/bin/env python3
"""Provision the 3 patient-intake function tools in Vapi and attach them to an
assistant, then point the assistant's server (end-of-call reports) at the same
webhook. Pure stdlib — no pip installs, no jq.

Usage:
    export VAPI_KEY="<your Vapi PRIVATE api key>"   # Vapi dashboard > API Keys
    export ASSISTANT_ID="<your assistant id>"        # top of the assistant page
    export VAPI_SECRET="<same as VAPI_SHARED_SECRET on Render>"
    python3 scripts/setup_vapi_tools.py

    # Preview the exact payloads without touching Vapi:
    python3 scripts/setup_vapi_tools.py --dry-run

Optional:
    export WEBHOOK="https://voice-patient-intake-ahyy.onrender.com/vapi/webhook"
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

API = "https://api.vapi.ai"
DEFAULT_WEBHOOK = "https://voice-patient-intake-ahyy.onrender.com/vapi/webhook"

SEX_ENUM = ["Male", "Female", "Other", "Decline to Answer"]
OPTIONAL_PROPS = {
    "address_line_2": {"type": "string"},
    "email": {"type": "string"},
    "insurance_provider": {"type": "string"},
    "insurance_member_id": {"type": "string"},
    "preferred_language": {"type": "string"},
    "emergency_contact_name": {"type": "string"},
    "emergency_contact_phone": {"type": "string"},
}

_REQUIRED_PROPS = {
    "first_name": {"type": "string"},
    "last_name": {"type": "string"},
    "date_of_birth": {"type": "string", "description": "MM/DD/YYYY"},
    "sex": {"type": "string", "enum": SEX_ENUM},
    "phone_number": {"type": "string"},
    "address_line_1": {"type": "string"},
    "city": {"type": "string"},
    "state": {"type": "string", "description": "2-letter US state code"},
    "zip_code": {"type": "string"},
}


def tool_defs(webhook: str, secret: str) -> list[dict]:
    # Any subset of patient fields can be sent incrementally.
    all_fields = {**_REQUIRED_PROPS, **OPTIONAL_PROPS}

    save_params = {
        "type": "object",
        "properties": {
            **all_fields,
            "start_over": {
                "type": "boolean",
                "description": "Set true to discard everything collected and restart.",
            },
        },
        "required": [],
    }
    finalize_params = {
        "type": "object",
        "properties": all_fields,  # optional last-minute fields
        "required": [],
    }
    update_params = {
        "type": "object",
        "properties": {"patient_id": {"type": "string"}, **all_fields},
        "required": ["patient_id"],
    }
    lookup_params = {
        "type": "object",
        "properties": {
            "phone_number": {"type": "string", "description": "Caller US phone number"}
        },
        "required": ["phone_number"],
    }
    server = {"url": webhook, "secret": secret}
    return [
        {
            "type": "function",
            "function": {
                "name": "lookup_patient_by_phone",
                "description": "Look up whether an existing patient has this phone "
                "number. Call as soon as you have the caller's phone number.",
                "parameters": lookup_params,
            },
            "server": server,
        },
        {
            "type": "function",
            "function": {
                "name": "save_patient_progress",
                "description": "Persist the patient fields collected SO FAR, in real "
                "time. Call it each time the caller gives a field, passing just that "
                "field. Returns what's still required, or VALIDATION_ERROR if a value "
                "is invalid (re-ask for that field). Pass start_over=true to reset.",
                "parameters": save_params,
            },
            "server": server,
        },
        {
            "type": "function",
            "function": {
                "name": "finalize_registration",
                "description": "Mark the patient as registered. Call ONLY after reading "
                "everything back and the caller confirms. Fails with INCOMPLETE if any "
                "required field is missing — never claim success without a SUCCESS result.",
                "parameters": finalize_params,
            },
            "server": server,
        },
        {
            "type": "function",
            "function": {
                "name": "update_patient",
                "description": "Update an existing registered patient (use the patient_id "
                "from lookup). Send only the fields that are changing.",
                "parameters": update_params,
            },
            "server": server,
        },
    ]


def load_system_prompt() -> str | None:
    """The agent prompt from vapi/system_prompt.md (everything after the --- rule)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vapi", "system_prompt.md")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return None
    parts = text.split("\n---\n", 1)
    body = (parts[1] if len(parts) == 2 else text).strip()
    return body or None


def _request(method: str, path: str, key: str, body: dict | None = None) -> dict:
    # Use curl as the HTTP client. (api.vapi.ai sits behind Cloudflare, which
    # rejects Python's default urllib user-agent with "error 1010"; curl's
    # standard client works normally.)
    cmd = [
        "curl", "-sS", "-X", method, f"{API}{path}",
        "-H", f"Authorization: Bearer {key}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
    ]
    if body is not None:
        cmd += ["-d", json.dumps(body)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"curl failed for {method} {path}: {proc.stderr.strip()}")
    out = (proc.stdout or "").strip()
    try:
        return json.loads(out or "{}")
    except json.JSONDecodeError:
        raise SystemExit(f"Vapi API {method} {path} returned non-JSON: {out}")


def main() -> None:
    dry = "--dry-run" in sys.argv
    webhook = os.getenv("WEBHOOK", DEFAULT_WEBHOOK)
    secret = os.getenv("VAPI_SECRET", "<VAPI_SECRET>" if dry else "")
    key = os.getenv("VAPI_KEY", "")
    assistant_id = os.getenv("ASSISTANT_ID", "")

    defs = tool_defs(webhook, secret)

    if dry:
        print("# DRY RUN — these payloads would be POSTed to", f"{API}/tool\n")
        for d in defs:
            print(json.dumps(d, indent=2))
            print()
        print("# Then PATCH /assistant/<id> would set model.toolIds + server + serverMessages.")
        return

    if not key or not assistant_id or not secret:
        raise SystemExit("Set VAPI_KEY, ASSISTANT_ID and VAPI_SECRET (see header).")

    print(f"Reading assistant {assistant_id} ...")
    assistant = _request("GET", f"/assistant/{assistant_id}", key)
    model = assistant.get("model") or {}
    old_tool_ids = list(model.get("toolIds") or [])

    print("Creating tools on Vapi...")
    tool_ids: list[str] = []
    for d in defs:
        created = _request("POST", "/tool", key, d)
        tid = created.get("id")
        if not tid:
            raise SystemExit(f"No id returned creating {d['function']['name']}: {created}")
        print(f"  {d['function']['name']:24} -> {tid}")
        tool_ids.append(tid)

    # Replace (not append) so re-running cleanly swaps the tool set.
    model["toolIds"] = tool_ids
    # Also push the current system prompt so Vapi matches the repo.
    prompt = load_system_prompt()
    if prompt:
        model["messages"] = [{"role": "system", "content": prompt}]
        print(f"Setting system prompt from vapi/system_prompt.md ({len(prompt)} chars)")
    else:
        print("WARNING: could not read vapi/system_prompt.md — leaving prompt unchanged")
    patch = {
        "model": model,
        "server": {"url": webhook, "secret": secret},
        "serverMessages": ["end-of-call-report", "status-update"],
    }
    print("Attaching new tools + prompt + wiring end-of-call webhook ...")
    updated = _request("PATCH", f"/assistant/{assistant_id}", key, patch)

    # Delete the now-detached old tools to keep the account tidy.
    for old in old_tool_ids:
        if old not in tool_ids:
            try:
                _request("DELETE", f"/tool/{old}", key)
                print(f"  removed old tool {old}")
            except SystemExit:
                pass

    print(json.dumps({
        "id": updated.get("id"),
        "name": updated.get("name"),
        "toolIds": (updated.get("model") or {}).get("toolIds"),
        "server": (updated.get("server") or {}).get("url"),
    }, indent=2))
    print("\nDone. Now Publish the assistant, then (re)claim/assign the phone number.")


if __name__ == "__main__":
    main()
