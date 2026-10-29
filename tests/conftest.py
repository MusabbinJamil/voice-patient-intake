"""Test harness: isolated SQLite file, no seeding, fresh schema per session."""
import os
import tempfile

import pytest

# Must be set BEFORE importing the app so config picks it up.
_TMP_DB = os.path.join(tempfile.gettempdir(), "patients_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["VAPI_SHARED_SECRET"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
