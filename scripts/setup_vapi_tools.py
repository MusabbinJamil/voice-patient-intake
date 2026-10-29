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
    register_params = {
        "type": "object",
        "properties": {**_REQUIRED_PROPS, **OPTIONAL_PROPS},
        "required": list(_REQUIRED_PROPS.keys()),
    }
    update_params = {
        "type": "object",
        "properties": {
            "patient_id": {"type": "string"},
            **_REQUIRED_PROPS,
            **OPTIONAL_PROPS,
        },
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
                "name": "register_patient",
                "description": "Create a new patient record. Only call AFTER reading "
                "all fields back and getting the caller's confirmation.",
                "parameters": register_params,
            },
            "server": server,
        },
        {
            "type": "function",
            "function": {
                "name": "update_patient",
                "description": "Update an existing patient (use the patient_id from "
                "lookup). Send only the fields that are changing.",
                "parameters": update_params,
            },
            "server": server,
        },
    ]


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

    print("Creating tools on Vapi...")
    tool_ids: list[str] = []
    for d in defs:
        created = _request("POST", "/tool", key, d)
        tid = created.get("id")
        if not tid:
            raise SystemExit(f"No id returned creating {d['function']['name']}: {created}")
        print(f"  {d['function']['name']:24} -> {tid}")
        tool_ids.append(tid)

    print(f"Reading assistant {assistant_id} ...")
    assistant = _request("GET", f"/assistant/{assistant_id}", key)
    model = assistant.get("model") or {}
    existing = model.get("toolIds") or []
    model["toolIds"] = list(dict.fromkeys(existing + tool_ids))  # dedupe, keep order

    patch = {
        "model": model,
        "server": {"url": webhook, "secret": secret},
        "serverMessages": ["end-of-call-report", "status-update"],
    }
    print("Attaching tools + wiring end-of-call webhook ...")
    updated = _request("PATCH", f"/assistant/{assistant_id}", key, patch)
    print(json.dumps({
        "id": updated.get("id"),
        "name": updated.get("name"),
        "toolIds": (updated.get("model") or {}).get("toolIds"),
        "server": (updated.get("server") or {}).get("url"),
    }, indent=2))
    print("\nDone. Now Publish the assistant, then claim a phone number and assign it.")


if __name__ == "__main__":
    main()
