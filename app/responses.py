"""Consistent JSON envelope: every REST response is `{"data": ..., "error": ...}`."""
from __future__ import annotations

from typing import Any, Optional

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def envelope(
    data: Any = None,
    error: Optional[dict] = None,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({"data": data, "error": error}),
    )


def error_body(code: int, message: str, details: Any = None) -> dict:
    body = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return body
