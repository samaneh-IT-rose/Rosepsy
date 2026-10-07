from typing import Any

from fastapi.responses import JSONResponse

from app.core.logging import request_id_var


def envelope(data: Any = None, errors: Any = None, extra_meta: dict | None = None) -> dict:
    """Standard response envelope { data, meta, errors } per API contract (doc s.10)."""
    meta = {"request_id": request_id_var.get(), "api_version": "v1"}
    if extra_meta:
        meta.update(extra_meta)
    return {"data": data, "meta": meta, "errors": errors}


def error_response(
    code: str,
    message: str,
    status_code: int,
    field: str | None = None,
    details: dict | None = None,
):
    error: dict = {"code": code, "message": message}
    if field:
        error["field"] = field
    if details:
        error.update(details)
    return JSONResponse(status_code=status_code, content=envelope(errors=[error]))
