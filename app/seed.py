"""Optional demo seed data.

Per the challenge FAQ, this is entirely fictional — no real patient data.
Seeding only runs when the patients table is empty.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select

from . import models
from .db import SessionLocal

logger = logging.getLogger("app.seed")

_SEED = [
    dict(
        first_name="Jane",
        last_name="Doe",
        date_of_birth=date(1985, 3, 15),
        sex="Female",
        phone_number="5125550142",
        email="jane.doe@example.com",
        address_line_1="100 Congress Ave",
        city="Austin",
        state="TX",
        zip_code="78701",
        insurance_provider="Blue Cross Blue Shield",
        insurance_member_id="BCBS123456",
        preferred_language="English",
    ),
    dict(
        first_name="Carlos",
        last_name="Ramirez",
        date_of_birth=date(1972, 11, 2),
        sex="Male",
        phone_number="3055550199",
        address_line_1="250 Ocean Dr",
        address_line_2="Apt 4B",
        city="Miami",
        state="FL",
        zip_code="33139",
        preferred_language="Spanish",
        emergency_contact_name="Maria Ramirez",
        emergency_contact_phone="3055550177",
    ),
]


def seed_if_empty() -> None:
    db = SessionLocal()
    try:
        if db.scalars(select(models.Patient).limit(1)).first() is not None:
            return
        db.add_all(models.Patient(**row) for row in _SEED)
        db.commit()
        logger.info("Seeded %d demo patients", len(_SEED))
    finally:
        db.close()
