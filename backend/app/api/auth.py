import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.schemas import envelope, error_response
from app.core import rate_limit
from app.core.config import settings
from app.core.db import get_db
from app.core.phone import InvalidPhone, mask_phone, normalize_iran_mobile
from app.core.redis_client import get_redis
from app.core.security import (
    codes_match,
    generate_otp_code,
    generate_session_token,
    hash_secret,
)
from app.models.core import AuthSession, OtpChallenge, Profile, User
from app.services.sms import get_sms_sender

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("roz.auth")


class OtpRequestIn(BaseModel):
    phone: str = Field(min_length=10, max_length=20)


class OtpVerifyIn(BaseModel):
    challenge_id: UUID
    code: str = Field(pattern=r"^\d{6}$")


@router.post("/otp/request")
def request_otp(body: OtpRequestIn, request: Request, db: Session = Depends(get_db)):
    """Issue a new OTP challenge (rate limited per phone and per IP)."""
    try:
        phone = normalize_iran_mobile(body.phone)
    except InvalidPhone:
        return error_response("INVALID_PHONE", "شماره موبایل معتبر نیست", 422, field="phone")

    ip = request.client.host if request.client else "-"
    redis = get_redis()
    try:
        ok_phone, ttl_phone = rate_limit.hit(
            redis,
            f"rl:otp:req:phone:{phone}",
            settings.OTP_REQUEST_LIMIT_PHONE,
            settings.OTP_RATE_WINDOW_SECONDS,
        )
        ok_ip, ttl_ip = rate_limit.hit(
            redis,
            f"rl:otp:req:ip:{ip}",
            settings.OTP_REQUEST_LIMIT_IP,
            settings.OTP_RATE_WINDOW_SECONDS,
        )
    except Exception:
        logger.exception("rate limit backend unavailable")
        return error_response("DEPENDENCY_UNAVAILABLE", "سرویس موقتا در دسترس نیست", 503)

    if not ok_phone:
        resp = error_response(
            "RATE_LIMITED", "تعداد درخواست کد برای این شماره زیاد است؛ کمی بعد تلاش کنید", 429
        )
        resp.headers["Retry-After"] = str(ttl_phone)
        return resp
    if not ok_ip:
        resp = error_response("RATE_LIMITED", "تعداد درخواست کد از این IP زیاد است", 429)
        resp.headers["Retry-After"] = str(ttl_ip)
        return resp

    if settings.ENV == "dev" and settings.SMS_PROVIDER == "dev_fixed":
        code = settings.DEV_FIXED_OTP_CODE  # fixed demo code (dev only)
    else:
        code = generate_otp_code(settings.OTP_CODE_LENGTH)
    now = datetime.now(UTC)
    # A fresh request supersedes previous open challenges for this phone.
    db.execute(
        update(OtpChallenge)
        .where(OtpChallenge.phone_e164 == phone)
        .where(OtpChallenge.consumed_at.is_(None))
        .values(expires_at=now)
    )
    challenge = OtpChallenge(
        phone_e164=phone,
        code_hash=hash_secret(code),
        max_attempts=settings.OTP_MAX_ATTEMPTS,
        expires_at=now + timedelta(seconds=settings.OTP_CODE_TTL_SECONDS),
        request_ip=ip,
    )
    db.add(challenge)
    db.commit()
    get_sms_sender().send_otp(phone, code)
    return envelope(
        data={
            "challenge_id": str(challenge.id),
            "phone_masked": mask_phone(phone),
            "expires_in_seconds": settings.OTP_CODE_TTL_SECONDS,
        }
    )


@router.post("/otp/verify")
def verify_otp(body: OtpVerifyIn, request: Request, db: Session = Depends(get_db)):
    """Verify once, then create the user (if new) and an auth session."""
    now = datetime.now(UTC)
    challenge = db.get(OtpChallenge, body.challenge_id)
    if challenge is None:
        return error_response("OTP_CHALLENGE_NOT_FOUND", "درخواست کد یافت نشد", 404)
    if challenge.consumed_at is not None:
        return error_response("OTP_ALREADY_USED", "این کد قبلا مصرف شده است", 409)
    if challenge.locked_until is not None and challenge.locked_until > now:
        return error_response("OTP_LOCKED", "به دلیل تلاش‌های ناموفق، موقتا قفل شده است", 423)
    if challenge.expires_at <= now:
        return error_response("OTP_EXPIRED", "اعتبار کد به پایان رسیده است", 400)

    if not codes_match(body.code, challenge.code_hash):
        challenge.attempts += 1
        if challenge.attempts >= challenge.max_attempts:
            challenge.locked_until = now + timedelta(seconds=settings.OTP_LOCK_SECONDS)
            db.commit()
            return error_response(
                "OTP_LOCKED", "تعداد تلاش‌های ناموفق زیاد بود؛ موقتا قفل شدید", 423
            )
        db.commit()
        return error_response("OTP_INVALID_CODE", "کد وارد شده صحیح نیست", 401)

    challenge.consumed_at = now
    user = db.execute(
        select(User).where(User.phone_e164 == challenge.phone_e164)
    ).scalar_one_or_none()
    is_new = user is None
    if is_new:
        user = User(phone_e164=challenge.phone_e164)
        db.add(user)
        db.flush()
        db.add(Profile(user_id=user.id))

    session_ttl = timedelta(seconds=settings.AUTH_SESSION_TTL_SECONDS)
    ip = request.client.host if request.client else "-"
    token = generate_session_token()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_secret(token),
            expires_at=now + session_ttl,
            ip=ip,
            user_agent=(request.headers.get("user-agent") or "-")[:255],
        )
    )
    db.commit()
    return envelope(
        data={
            "access_token": token,
            "token_type": "bearer",
            "expires_at": (now + session_ttl).isoformat(),
            "is_new_user": is_new,
            "user": {"id": str(user.id), "phone": user.phone_e164},
        }
    )
