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
    """Development sender (D04 open): the code goes to the app log AND to
    backend/logs/dev-otp.log so the manual test flow can read it easily.

    It must never appear in an HTTP response. Real providers (kavenegar /
    faraz / ...) plug in behind this interface once D04 is decided.
    """

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


_MOCK = MockSmsSender()


def get_sms_sender() -> SmsSender:
    if settings.SMS_PROVIDER != "mock":
        raise RuntimeError(f"unknown SMS_PROVIDER={settings.SMS_PROVIDER}")
    return _MOCK
