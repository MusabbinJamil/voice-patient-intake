"""Pydantic schemas: request validation + response serialization.

`PatientCreate` enforces all required fields; `PatientUpdate` makes every field
optional for partial (PUT) updates. Both run the same normalization/validation
helpers so the API and the voice agent share one definition of "valid".
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from . import validators as v


class PatientCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    address_line_1: str
    city: str
    state: str
    zip_code: str

    email: Optional[str] = None
    address_line_2: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: str = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def _names(cls, value):
        return v.validate_name(value)

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob(cls, value):
        return v.parse_dob(value)

    @field_validator("sex", mode="before")
    @classmethod
    def _sex(cls, value):
        return v.normalize_sex(value)

    @field_validator("phone_number", mode="before")
    @classmethod
    def _phone(cls, value):
        return v.validate_phone(value)

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def _emg_phone(cls, value):
        if value in (None, ""):
            return None
        return v.validate_phone(value)

    @field_validator("state", mode="before")
    @classmethod
    def _state(cls, value):
        return v.validate_state(value)

    @field_validator("zip_code", mode="before")
    @classmethod
    def _zip(cls, value):
        return v.validate_zip(value)

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, value):
        if value in (None, ""):
            return None
        return v.validate_email(value)


class PatientUpdate(BaseModel):
    """All fields optional; only those supplied are changed."""

    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    phone_number: Optional[str] = None
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    email: Optional[str] = None
    address_line_2: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def _names(cls, value):
        return None if value is None else v.validate_name(value)

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob(cls, value):
        return None if value is None else v.parse_dob(value)

    @field_validator("sex", mode="before")
    @classmethod
    def _sex(cls, value):
        return None if value is None else v.normalize_sex(value)

    @field_validator("phone_number", "emergency_contact_phone", mode="before")
    @classmethod
    def _phone(cls, value):
        return None if value in (None, "") else v.validate_phone(value)

    @field_validator("state", mode="before")
    @classmethod
    def _state(cls, value):
        return None if value is None else v.validate_state(value)

    @field_validator("zip_code", mode="before")
    @classmethod
    def _zip(cls, value):
        return None if value is None else v.validate_zip(value)

    @field_validator("email", mode="before")
    @classmethod
    def _email(cls, value):
        return None if value in (None, "") else v.validate_email(value)


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: uuid.UUID
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    email: Optional[str] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    zip_code: str
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: str
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
