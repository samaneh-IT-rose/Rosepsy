import logging
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import text

from app.api.schemas import envelope
from app.core.config import settings
from app.core.db import engine

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict:
    """Liveness probe (B01): process is up; no dependency checks."""
    return envelope(data={"status": "ok", "env": settings.ENV, "version": settings.APP_VERSION})


@router.get("/ready")
def ready():
    """Readiness probe (B01): verifies DB and Redis connectivity."""
    checks: dict[str, str] = {}
    start = time.perf_counter()

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        logger.warning("readiness db check failed: %s", exc)
        checks["db"] = "fail"

    try:
        client = Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        try:
            client.ping()
        finally:
            client.close()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.warning("readiness redis check failed: %s", exc)
        checks["redis"] = "fail"

    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    ok = all(v == "ok" for v in checks.values())

    body = envelope(
        data={"status": "ready" if ok else "not_ready", "checks": checks, "elapsed_ms": elapsed_ms},
        errors=None
        if ok
        else [{"code": "DEPENDENCY_UNAVAILABLE", "message": "یک یا چند وابستگی سرویس در دسترس نیست"}],
    )
    return JSONResponse(status_code=200 if ok else 503, content=body)
