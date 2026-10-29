"""Application configuration, loaded entirely from environment variables.

No secrets live in source. Locally, values come from a `.env` file (see
`.env.example`) that is loaded here if python-dotenv is installed; in
production (Render) they come from the dashboard's environment settings.
"""
from __future__ import annotations

import os

try:  # optional: makes local dev nicer, not required in production
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is a dev convenience only
    pass


class Settings:
    def __init__(self) -> None:
        # Postgres in production (Neon); SQLite fallback for zero-setup local dev.
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./patients.db")

        # Shared secret that Vapi sends in the `x-vapi-secret` header on every
        # server request. When empty (local dev) verification is skipped.
        self.vapi_shared_secret: str = os.getenv("VAPI_SHARED_SECRET", "")

        # Seed 1-2 demo rows on first boot when the table is empty.
        self.seed_on_startup: bool = os.getenv("SEED_ON_STARTUP", "true").lower() == "true"

        self.app_env: str = os.getenv("APP_ENV", "development")


settings = Settings()
