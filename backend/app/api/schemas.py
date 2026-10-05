from typing import Any

from app.core.logging import request_id_var


def envelope(data: Any = None, errors: Any = None) -> dict:
    """Standard response envelope { data, meta, errors } per API contract (doc section 10)."""
    return {
        "data": data,
        "meta": {"request_id": request_id_var.get(), "api_version": "v1"},
        "errors": errors,
    }
