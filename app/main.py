"""FastAPI application entrypoint.

Wires routers, installs exception handlers that keep the {data, error} envelope
consistent even for errors, creates tables on startup, and seeds demo data.

We use create_all() on startup instead of Alembic migrations — a deliberate
trade-off for a time-boxed project (documented in the README).
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .db import Base, engine
from .dashboard import router as dashboard_router
from .migrate import ensure_schema
from .responses import envelope, error_body
from .routers.patients import router as patients_router
from .routers.vapi import router as vapi_router
from .seed import seed_if_empty

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create tables on startup (create_all over Alembic — documented trade-off),
    # then evolve any pre-existing table to the current (draft-aware) schema
    # without dropping data.
    Base.metadata.create_all(bind=engine)
    ensure_schema(engine)
    if settings.seed_on_startup:
        seed_if_empty()
    logger.info("Startup complete (env=%s)", settings.app_env)
    yield


app = FastAPI(
    title="Voice AI Patient Registration",
    version="1.0.0",
    description="Telephony voice agent + REST API + dashboard for patient intake.",
    lifespan=lifespan,
)

# Dashboard is browser-facing; allow any origin to read the public API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Exception handlers: always return the envelope ---

@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    from fastapi.encoders import jsonable_encoder

    return envelope(
        error=error_body(422, "Validation failed", jsonable_encoder(exc.errors())),
        status_code=422,
    )


@app.exception_handler(StarletteHTTPException)
async def http_handler(request: Request, exc: StarletteHTTPException):
    return envelope(
        error=error_body(exc.status_code, str(exc.detail)),
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error")
    return envelope(error=error_body(500, "Internal server error"), status_code=500)


# --- Routers ---
app.include_router(patients_router)
app.include_router(vapi_router)
app.include_router(dashboard_router)


@app.get("/health", tags=["meta"])
def health():
    """Liveness + DB connectivity check (also used by the keep-warm pinger)."""
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover
        db_ok = False
    return envelope({"status": "ok", "database": "ok" if db_ok else "down"})


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard")
