# Voice AI Patient Registration

A voice AI agent you call on a real US phone number. It greets you, collects your
patient demographics in natural conversation, reads them back for confirmation,
and saves them to a persistent database. A REST API and a small web dashboard
expose the stored records. Call back later and your record is still there.

**Live (fill in after deploy):**
- 📞 Phone: `+1 (XXX) XXX-XXXX`
- 🌐 API base URL: `https://YOUR_APP.onrender.com`
- 📊 Dashboard: `https://YOUR_APP.onrender.com/dashboard`

---

## Architecture

```
 Caller's phone ──PSTN──▶  Vapi number
                            │   Vapi runs STT, TTS, barge-in, and the
                            │   conversation loop with the LLM (Groq Llama 3.3).
                            │   It calls our server over HTTPS for data.
                            ▼
      FastAPI (Render, free)  ──SQLAlchemy──▶  Postgres (Neon, free)
        ├── REST  /patients          CRUD + soft delete + query params
        ├── Voice /vapi/webhook       tool calls + end-of-call transcript
        ├── View  /dashboard          HTML table of patients + call logs
        └── Meta  /health             liveness + DB check (keep-warm target)
```

**Separation of concerns** is deliberate:
- **Telephony / STT / TTS** → Vapi (configured, not coded — see `vapi/`).
- **Conversation logic** → the LLM system prompt in `vapi/system_prompt.md`.
- **Validation + persistence** → `app/` (the voice agent and the REST API share
  the *same* validators and data layer, so the agent cannot bypass server-side
  validation).
- **Data layer** → SQLAlchemy models + CRUD, swappable DB engine.

## Tech stack & why

| Layer | Choice | Why |
|---|---|---|
| Telephony + voice | **Vapi** | Abstracts STT/TTS/turn-taking/barge-in; free tier includes a US inbound number and credits. Fastest path to a natural-sounding agent. |
| LLM | **Groq `llama-3.3-70b-versatile`** (BYOK into Vapi) | Free API tier, very low latency (good for voice), strong instruction following. Conserves Vapi credits. |
| Backend | **FastAPI** (Python) | Async, first-class Pydantic validation, auto OpenAPI docs, minimal boilerplate. |
| ORM / validation | **SQLAlchemy 2.0** + **Pydantic v2** | Portable schema (Postgres ↔ SQLite), one validation definition reused by API and agent. |
| Database | **Neon Postgres** | Free, truly persistent, scale-to-zero with sub-second wake, and (unlike Supabase free) no weekly inactivity pause. |
| Hosting | **Render** (free web service) | Free, simple Git deploy via `render.yaml`. |

All free. See **Known limitations** for the trade-offs this implies.

## Data model

Table `patients` (see `app/models.py`). Required unless marked optional.

| Field | Type | Rules |
|---|---|---|
| `patient_id` | UUID | auto (PK) |
| `first_name`, `last_name` | str(50) | letters, spaces, `-`, `'` |
| `date_of_birth` | date | valid, not future, ≥ 1900 |
| `sex` | str | `Male` / `Female` / `Other` / `Decline to Answer` (DB CHECK constraint) |
| `phone_number` | str(10) | normalized to 10 digits, area code 2–9 |
| `address_line_1` | str | required |
| `city` | str(100) | required |
| `state` | str(2) | valid US abbreviation |
| `zip_code` | str | `#####` or `#####-####` |
| `email` | str | optional, format-checked |
| `address_line_2` | str | optional |
| `insurance_provider`, `insurance_member_id` | str | optional |
| `preferred_language` | str | optional, default `English` |
| `emergency_contact_name` | str | optional |
| `emergency_contact_phone` | str(10) | optional, validated |
| `created_at`, `updated_at` | timestamptz | auto, UTC |
| `deleted_at` | timestamptz | soft-delete marker (null = active) |

Table `call_logs` stores each call's transcript + summary + structured payload,
linked to a patient by phone when possible (observability + transcript bonus).

## REST API

Base: `https://YOUR_APP.onrender.com`. Every response is
`{"data": <payload-or-null>, "error": <null-or-{code,message,details}>}`.

| Method | Path | Notes |
|---|---|---|
| GET | `/patients` | list active; filters `?last_name=` `?date_of_birth=` `?phone_number=` |
| GET | `/patients/{id}` | 404 if missing or soft-deleted |
| POST | `/patients` | 201 on success, 422 on validation error |
| PUT | `/patients/{id}` | partial update |
| DELETE | `/patients/{id}` | soft delete (sets `deleted_at`) |
| GET | `/health` | liveness + DB check |
| GET | `/docs` | auto OpenAPI/Swagger UI |

Status codes: 200 / 201 / 404 / 422 / 500. Validation is **server-side** via
Pydantic — the agent is never trusted as the only gate.

```bash
# Create
curl -X POST https://YOUR_APP.onrender.com/patients \
  -H 'content-type: application/json' \
  -d '{"first_name":"Jane","last_name":"Doe","date_of_birth":"03/15/1985",
       "sex":"Female","phone_number":"(512) 555-0142","address_line_1":"100 Congress Ave",
       "city":"Austin","state":"TX","zip_code":"78701"}'

# List / filter
curl 'https://YOUR_APP.onrender.com/patients?last_name=Doe'

# Update (partial)
curl -X PUT https://YOUR_APP.onrender.com/patients/<id> \
  -H 'content-type: application/json' -d '{"city":"Dallas"}'

# Soft delete
curl -X DELETE https://YOUR_APP.onrender.com/patients/<id>
```

## Voice agent ↔ data integration

The Vapi assistant has three function tools, all pointed at `/vapi/webhook`:

- `lookup_patient_by_phone` — called early; enables returning-caller detection.
- `register_patient` — called only after read-back confirmation → `POST` equivalent.
- `update_patient` — for returning callers who choose to update.

The webhook validates the agent's arguments with the same Pydantic schema as the
API and returns a plain-language result the LLM relays to the caller:
- `SUCCESS …` → agent confirms ("You're all set, Jane.")
- `VALIDATION_ERROR … <field> …` → agent re-prompts for that specific field
- `DUPLICATE …` / `FOUND …` → agent offers to update instead
- `SAVE_FAILED …` → agent apologizes; never claims a false success

## Project structure

```
app/
  main.py          FastAPI app, lifespan (create tables + seed), envelope error handlers
  config.py        env-var settings
  db.py            engine/session (Postgres or SQLite)
  models.py        Patient, CallLog
  schemas.py       PatientCreate / PatientUpdate / PatientOut
  validators.py    phone/name/state/zip/email/DOB/sex rules (shared)
  crud.py          data-access layer
  responses.py     {data, error} envelope helper
  dashboard.py     server-rendered HTML dashboard
  seed.py          fictional demo rows
  routers/
    patients.py    REST endpoints
    vapi.py        voice webhook (tools + end-of-call report)
vapi/
  system_prompt.md the LLM system message, documented
  assistant.json   importable Vapi assistant + tool definitions
tests/             pytest API + voice-tool integration tests
render.yaml        Render blueprint
docs/keepalive.github-actions.yml  optional keep-warm workflow (activation notes inside)
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # optional; without it, a local SQLite file is used
uvicorn app.main:app --reload --port 8000
# open http://localhost:8000/dashboard  and  http://localhost:8000/docs
pytest -q                    # 12 passing tests
```

No `DATABASE_URL` → the app uses `sqlite:///./patients.db` for zero-setup dev.

## Deployment & provider setup

See **SETUP** below (also reproduced in the submission message). In short:
1. **Neon** → create project, copy the Postgres URL.
2. **Render** → deploy this repo via `render.yaml`; set `DATABASE_URL` and
   `VAPI_SHARED_SECRET` env vars.
3. **Groq** → create a free API key.
4. **Vapi** → create the assistant (paste `system_prompt.md`, add the 3 tools
   from `assistant.json` pointed at `/vapi/webhook` with the secret, select the
   Groq model with your key), attach the free phone number, set the server URL.
5. **Keep-warm** → create a free monitor at cron-job.org pinging
   `/health` every 10 min (or activate `docs/keepalive.github-actions.yml`).

## Environment variables

| Var | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | prod | Neon Postgres URL (SQLite fallback locally) |
| `VAPI_SHARED_SECRET` | prod | shared secret verified on `/vapi/webhook` |
| `SEED_ON_STARTUP` | no | seed demo rows when table empty (default true) |
| `APP_ENV` | no | label only |

No secrets are committed; `.env` is git-ignored.

## Observability

- `POST /patients` logs the persisted payload to stdout (`PATIENT_CREATED …`).
- Voice writes log `PATIENT_CREATED via voice …`.
- End-of-call reports log `CALL_ENDED …` and store the full transcript in
  `call_logs`, visible on the dashboard.

## Security notes

- Secrets live only in environment variables.
- `/vapi/webhook` requires the `x-vapi-secret` header to match `VAPI_SHARED_SECRET`.
- All input is validated and normalized server-side before it touches the DB.
- Per the challenge FAQ, **only fictional data** is stored — not real PHI.

## Known limitations & trade-offs (intentional for a 3-hour build)

- **`create_all()` instead of Alembic migrations.** Fine for a greenfield demo;
  a real system needs versioned migrations.
- **Render free tier cold start (~1 min).** Mitigated by a 10-min keep-warm ping
  (cron-job.org or the optional GitHub Action in `docs/`);
  if the service still napped, the first call's DB write could be slow. (The
  database itself is always persistent on Neon — data never lost on restart.)
- **No auth on the REST API.** The dashboard and API are public for easy review.
  Production would need auth/RBAC and rate limiting.
- **Duplicate detection is phone-based** and blocks a second create on the same
  number; genuine shared-phone households would need a smarter rule.
- **Soft delete only**; no restore endpoint exposed.

## Bonus features implemented

- ✅ **Duplicate detection** (returning caller by phone → offer update)
- ✅ **Multi-language** (agent switches to Spanish; stored as `preferred_language`)
- ✅ **Call transcript** stored and linked to the patient (`call_logs`)
- ✅ **Dashboard** (`/dashboard`)
- ✅ **Automated tests** (`tests/`, 12 cases incl. voice-tool round-trip)

## Next steps (if I had more time)

- Alembic migrations; auth + rate limiting on the API.
- Appointment scheduling tool after registration (mock slots).
- Structured per-field confirmation state machine + a retry queue for failed writes.
- Richer dashboard (search, pagination, edit, deleted-record view).
- E.164 phone storage and libphonenumber-grade validation.
