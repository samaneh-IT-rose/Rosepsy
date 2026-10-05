from typing import Any

from fastapi.responses import JSONResponse

from app.core.logging import request_id_var


def envelope(data: Any = None, errors: Any = None) -> dict:
    """Standard response envelope { data, meta, errors } per API contract (doc section 10)."""
    return {
        "data": data,
        "meta": {"request_id": request_id_var.get(), "api_version": "v1"},
        "errors": errors,
    }


def error_response(code: str, message: str, status_code: int, field: str | None = None):
    error: dict = {"code": code, "message": message}
    if field:
        error["field"] = field
    return JSONResponse(status_code=status_code, content=envelope(errors=[error]))
