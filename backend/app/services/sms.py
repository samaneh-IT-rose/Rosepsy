"""SMS sending (B02/B38). Providers (D04 open) plug in behind SmsSender.

- MockSmsSender: logs the code (and keeps in-memory capture for tests).
- DevFixedSmsSender: dev/acceptance convenience - a FIXED code (default
  123456) so deliveries can be demoed without reading server logs.
  It is ONLY reachable when ENV=dev; any other env raises at startup.
"""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("roz.sms")


class SmsSender(ABC):
    @abstractmethod
    def send_otp(self, phone_e164: str, code: str) -> None: ...


class MockSmsSender(SmsSender):
    """Logs the code and captures it in memory (used by the test suite)."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self._file = Path("logs/dev-otp.log")

    def send_otp(self, phone_e164: str, code: str) -> None:
        self.sent.append({"phone": phone_e164, "code": code})
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            with self._file.open("a", encoding="utf-8") as f:
                f.write(f"{stamp}\t{phone_e164}\t{code}\n")
        except OSError:
            logger.warning("could not append to dev OTP log file", exc_info=True)
        logger.info(
            "sms mock sent to=%s code=%s (provider=mock env=%s)",
            phone_e164,
            code,
            settings.ENV,
        )


class DevFixedSmsSender(SmsSender):
    """Fixed code for dev/acceptance demos (no log reading needed).
    The fixed code never leaves the server; the API response stays clean."""

    def __init__(self, fixed_code: str = "123456") -> None:
        self.fixed_code = fixed_code

    def send_otp(self, phone_e164: str, code: str) -> None:
        logger.info(
            "sms dev-fixed to=%s (provider=dev_fixed env=%s) -> use code %s",
            phone_e164,
            settings.ENV,
            self.fixed_code,
        )


_MOCK = MockSmsSender()
_DEV_FIXED = DevFixedSmsSender(settings.DEV_FIXED_OTP_CODE)


def get_sms_sender() -> SmsSender:
    if settings.ENV == "dev" and settings.SMS_PROVIDER == "dev_fixed":
        return _DEV_FIXED
    if settings.SMS_PROVIDER == "mock":
        return _MOCK
    raise RuntimeError(f"unknown SMS_PROVIDER={settings.SMS_PROVIDER}")
