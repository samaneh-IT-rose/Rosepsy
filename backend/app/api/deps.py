from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import hash_secret
from app.models.core import AuthSession, User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Bearer token backed by core.auth_sessions (opaque token, hashed at rest)."""
    auth_header = request.headers.get("authorization") or ""
    if not auth_header.startswith("Bearer "):
        _deny()
    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        _deny()
    session = db.execute(
        select(AuthSession).where(AuthSession.token_hash == hash_secret(token))
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        _deny()
    user = db.get(User, session.user_id)
    if user is None or user.status != "active":
        _deny()
    return user


def _deny() -> None:
    raise HTTPException(status_code=401, detail="UNAUTHORIZED")
