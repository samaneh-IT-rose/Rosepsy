import hashlib
import hmac
import secrets

from app.core.config import settings


def generate_otp_code(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    """HMAC-SHA256 with server pepper; deterministic so hashed values stay lookable."""
    return hmac.new(settings.OTP_PEPPER.encode(), value.encode(), hashlib.sha256).hexdigest()


def codes_match(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(code), code_hash)
