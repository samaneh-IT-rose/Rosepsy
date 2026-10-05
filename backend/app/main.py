import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api import health
from app.core.config import settings
from app.core.logging import request_id_var, setup_logging

setup_logging(level=settings.LOG_LEVEL)
logger = logging.getLogger("roz.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "startup app=%s env=%s version=%s", settings.APP_NAME, settings.ENV, settings.APP_VERSION
    )
    yield
    logger.info("shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Assign/propagate X-Request-ID for error tracing (B01)."""
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = rid
        logger.info(
            "http %s %s -> %s (%sms)", request.method, request.url.path, response.status_code, duration_ms
        )
        return response
    finally:
        request_id_var.reset(token)


app.include_router(health.router)


@app.get("/")
def root() -> dict:
    return {"name": settings.APP_NAME, "docs": "/docs"}
