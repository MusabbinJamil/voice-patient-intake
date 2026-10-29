"""Reusable field-level validation and normalization helpers.

These are the single source of truth for what counts as valid data. They are
used by the Pydantic schemas (so the REST API validates server-side) *and* by
the voice-agent tool layer (so the agent can never bypass validation).
"""
from __future__ import annotations

import re
from datetime import date, datetime

# 50 states + DC + common US territories.
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC", "PR", "VI", "GU", "AS", "MP",
}

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z' \-]{0,49}$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_SEX_MAP = {
    "m": "Male",
    "male": "Male",
    "f": "Female",
    "female": "Female",
    "o": "Other",
    "other": "Other",
    "decline": "Decline to Answer",
    "decline to answer": "Decline to Answer",
    "prefer not to say": "Decline to Answer",
}

_DOB_FORMATS = (
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%m-%d-%Y",
    "%m/%d/%y",
    # Spoken / natural-language forms, in case the agent passes them through.
    "%B %d %Y",
    "%B %d, %Y",
    "%b %d %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
)


def normalize_phone(value: str) -> str:
    """Strip to bare digits and drop a leading US country code."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def validate_phone(value: str) -> str:
    digits = normalize_phone(value)
    if len(digits) != 10 or digits[0] in "01":
        raise ValueError("must be a valid US 10-digit phone number")
    return digits


def validate_name(value: str) -> str:
    v = str(value or "").strip()
    if not NAME_RE.match(v):
        raise ValueError("must be 1-50 letters, spaces, hyphens or apostrophes")
    return v


def validate_state(value: str) -> str:
    v = str(value or "").strip().upper()
    if v not in US_STATES:
        raise ValueError("must be a valid 2-letter US state abbreviation")
    return v


def validate_zip(value: str) -> str:
    v = str(value or "").strip()
    if not ZIP_RE.match(v):
        raise ValueError("must be a 5-digit or ZIP+4 US ZIP code")
    return v


def validate_email(value: str) -> str:
    v = str(value or "").strip()
    if not EMAIL_RE.match(v):
        raise ValueError("must be a valid email address")
    return v


def normalize_sex(value: str) -> str:
    v = str(value or "").strip()
    mapped = _SEX_MAP.get(v.lower())
    if mapped:
        return mapped
    raise ValueError("must be one of Male, Female, Other, Decline to Answer")


def parse_dob(value) -> date:
    """Parse a date of birth, accepting MM/DD/YYYY and ISO; reject the future."""
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        s = str(value or "").strip()
        d = None
        for fmt in _DOB_FORMATS:
            try:
                d = datetime.strptime(s, fmt).date()
                break
            except ValueError:
                continue
        if d is None:
            raise ValueError("must be a valid date in MM/DD/YYYY format")
    if d > date.today():
        raise ValueError("date of birth cannot be in the future")
    if d.year < 1900:
        raise ValueError("date of birth year is out of range")
    return d
