import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import (
    applicants,
    audit,
    auth,
    availability,
    booking,
    catalog,
    clinical,
    clinics,
    consents,
    consultants,
    files,
    health,
    invoices,
    me,
    notifications,
    orders,
    pricing,
    roles,
    topics,
)
from app.api.schemas import envelope
from app.core.config import settings
from app.core.logging import request_id_var, setup_logging

setup_logging(level=settings.LOG_LEVEL)
logger = logging.getLogger("roz.http")

ERROR_MESSAGES = {
    "UNAUTHORIZED": "احراز هویت لازم است",
    "FORBIDDEN": "دسترسی غیرمجاز است",
}


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
            "http %s %s -> %s (%sms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
    finally:
        request_id_var.reset(token)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Render HTTP errors in the standard envelope with Persian messages (contract s.10)."""
    code = str(exc.detail)
    message = ERROR_MESSAGES.get(code, "درخواست قابل قبول نیست")
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(errors=[{"code": code, "message": message}]),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for raw in exc.errors():
        loc = raw.get("loc", [])
        field_name = str(loc[-1]) if len(loc) > 1 else None
        errors.append(
            {"code": "VALIDATION_ERROR", "message": "ورودی نامعتبر است", "field": field_name}
        )
    return JSONResponse(status_code=422, content=envelope(errors=errors))


app.include_router(health.router)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(me.router, prefix=settings.API_V1_PREFIX)
app.include_router(applicants.router, prefix=settings.API_V1_PREFIX)
app.include_router(roles.router, prefix=settings.API_V1_PREFIX)
app.include_router(catalog.router, prefix=settings.API_V1_PREFIX)
app.include_router(consultants.router, prefix=settings.API_V1_PREFIX)
app.include_router(clinics.router, prefix=settings.API_V1_PREFIX)
app.include_router(pricing.router, prefix=settings.API_V1_PREFIX)
app.include_router(topics.router, prefix=settings.API_V1_PREFIX)
app.include_router(availability.router, prefix=settings.API_V1_PREFIX)
app.include_router(booking.router, prefix=settings.API_V1_PREFIX)
app.include_router(orders.router, prefix=settings.API_V1_PREFIX)
app.include_router(invoices.router, prefix=settings.API_V1_PREFIX)
app.include_router(notifications.router, prefix=settings.API_V1_PREFIX)
app.include_router(files.router, prefix=settings.API_V1_PREFIX)
app.include_router(consents.router, prefix=settings.API_V1_PREFIX)
app.include_router(audit.router, prefix=settings.API_V1_PREFIX)
app.include_router(clinical.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root() -> dict:
    return {"name": settings.APP_NAME, "docs": "/docs"}
