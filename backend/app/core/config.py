from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables (12-factor)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Roz Clinic API"
    APP_VERSION: str = "0.1.0"
    ENV: str = "dev"  # dev | test | staging | prod
    LOG_LEVEL: str = "INFO"

    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+psycopg://roz:roz_dev@localhost:5432/roz"
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- B02 / OTP & sessions ---
    OTP_PEPPER: str = "dev-pepper-change-me"
    OTP_CODE_LENGTH: int = 6
    OTP_CODE_TTL_SECONDS: int = 120
    OTP_MAX_ATTEMPTS: int = 5
    OTP_LOCK_SECONDS: int = 900
    OTP_REQUEST_LIMIT_PHONE: int = 3
    OTP_REQUEST_LIMIT_IP: int = 20
    OTP_RATE_WINDOW_SECONDS: int = 600
    AUTH_SESSION_TTL_SECONDS: int = 7 * 24 * 3600
    SMS_PROVIDER: str = "mock"  # D04 open; mock logs the code only

    # --- B08 / availability ---
    AVAILABILITY_TIMEZONE: str = "Asia/Tehran"

    # --- B09 / booking (spec s.10 example: hold TTL = 10 minutes) ---
    BOOKING_HOLD_TTL_SECONDS: int = 600
    BOOKING_MAX_ADVANCE_DAYS: int = 31

    # --- B10 / payments (D02 open) ---
    PAYMENT_GATEWAY: str = "mock"
    # Comma-separated gateway IPs allowed to call /payments/callback.
    # Empty = unrestricted (dev only); production MUST set it.
    PAYMENT_CALLBACK_ALLOWLIST: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

