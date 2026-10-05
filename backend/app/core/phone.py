"""Phone normalization (global rule: one canonical mobile format)."""

import re

_IR_MOBILE = re.compile(r"^(?:\+98|0098|98|0)?9\d{9}$")


class InvalidPhone(ValueError):
    pass


def normalize_iran_mobile(raw: str) -> str:
    """Normalize to E.164 (+989XXXXXXXXX); raises InvalidPhone otherwise."""
    digits = (raw or "").strip().replace(" ", "").replace("-", "")
    if not _IR_MOBILE.match(digits):
        raise InvalidPhone("شماره موبایل معتبر نیست")
    local = digits[-10:]  # 9XXXXXXXXX
    return "+98" + local


def mask_phone(phone_e164: str) -> str:
    return f"{phone_e164[:6]}***{phone_e164[-3:]}"
