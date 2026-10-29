"""Minimal server-rendered dashboard at GET /dashboard.

Lists registered patients and recent call transcripts straight from the DB.
Intentionally dependency-free (no JS framework) so it is one file, one URL,
served by the same app.
"""
from __future__ import annotations

import html
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from . import crud
from .db import get_db

router = APIRouter(tags=["dashboard"])


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _fmt_dt(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M UTC")
    return _esc(value)


_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  margin: 0; padding: 24px; background: #0f1115; color: #e6e8ee; }
@media (prefers-color-scheme: light) { body { background: #f6f7f9; color: #15171c; } }
h1 { font-size: 20px; margin: 0 0 4px; }
.sub { opacity: .65; font-size: 13px; margin-bottom: 20px; }
.card { background: rgba(127,127,127,.08); border: 1px solid rgba(127,127,127,.18);
  border-radius: 12px; padding: 16px; margin-bottom: 24px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid rgba(127,127,127,.15);
  white-space: nowrap; }
th { font-weight: 600; opacity: .7; text-transform: uppercase; font-size: 11px; letter-spacing: .04em; }
tr:last-child td { border-bottom: none; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: rgba(90,160,255,.18); }
.empty { opacity: .6; padding: 16px; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; opacity: .8; }
pre { white-space: pre-wrap; margin: 0; font-size: 12px; max-width: 900px;
  max-height: 280px; overflow: auto; }
.summary { font-weight: 600; margin-bottom: 6px; }
"""


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(db: Session = Depends(get_db)):
    patients = crud.list_patients(db)
    logs = crud.recent_call_logs(db, limit=8)

    if patients:
        rows = "\n".join(
            f"<tr><td class='mono'>{_esc(str(p.patient_id)[:8])}</td>"
            f"<td>{_esc(p.first_name)} {_esc(p.last_name)}</td>"
            f"<td>{_esc(p.date_of_birth)}</td>"
            f"<td>{_esc(p.sex)}</td>"
            f"<td class='mono'>{_esc(p.phone_number)}</td>"
            f"<td>{_esc(p.city)}, {_esc(p.state)} {_esc(p.zip_code)}</td>"
            f"<td>{_esc(p.insurance_provider)}</td>"
            f"<td>{_esc(p.preferred_language)}</td>"
            f"<td>{_fmt_dt(p.created_at)}</td></tr>"
            for p in patients
        )
        patients_html = (
            "<table><thead><tr>"
            "<th>ID</th><th>Name</th><th>DOB</th><th>Sex</th><th>Phone</th>"
            "<th>Location</th><th>Insurance</th><th>Lang</th><th>Created</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    else:
        patients_html = "<div class='empty'>No patients yet. Call the number to register one.</div>"

    if logs:
        log_items = "\n".join(
            f"<tr><td>{_fmt_dt(lg.created_at)}</td>"
            f"<td class='mono'>{_esc(lg.phone_number)}</td>"
            f"<td>"
            + (f"<div class='summary'>{_esc(lg.summary)}</div>" if lg.summary else "")
            + f"<pre>{_esc(lg.transcript or '(no transcript)')}</pre>"
            + "</td></tr>"
            for lg in logs
        )
        logs_html = (
            "<table><thead><tr><th>When</th><th>Caller</th><th>Summary / Transcript</th></tr>"
            f"</thead><tbody>{log_items}</tbody></table>"
        )
    else:
        logs_html = "<div class='empty'>No call transcripts yet.</div>"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Patient Intake Dashboard</title><style>{_STYLE}</style></head>
<body>
  <h1>Patient Intake Dashboard</h1>
  <div class="sub">{len(patients)} active patient(s) · live from the database · demo data is fictional</div>
  <div class="card"><h2 style="font-size:14px;margin:0 0 12px">Patients</h2>{patients_html}</div>
  <div class="card"><h2 style="font-size:14px;margin:0 0 12px">Recent Calls <span class="badge">transcripts</span></h2>{logs_html}</div>
</body></html>"""
