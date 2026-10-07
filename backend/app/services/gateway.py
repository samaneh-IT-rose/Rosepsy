"""Payment gateway adapter (B10). D02 is open: MockGateway now; a real
provider (Zarinpal/IDPay/...) plugs in behind the same interface later."""

import uuid
from abc import ABC, abstractmethod

from app.core.config import settings


class PaymentGateway(ABC):
    name: str

    @abstractmethod
    def start(self, *, order_id: uuid.UUID, amount: int, currency: str) -> tuple[str, str]:
        """Returns (gateway_ref, redirect_url)."""

    @abstractmethod
    def verify(self, *, payload: dict) -> tuple[bool, dict]:
        """Server-side verification of a callback. Returns (ok, raw_payload)."""


class MockGateway(PaymentGateway):
    """Development gateway: callback verification trusts the submitted result;
    idempotency and state transitions are enforced by the payments endpoint."""

    name = "mock"

    def start(self, *, order_id: uuid.UUID, amount: int, currency: str) -> tuple[str, str]:
        ref = f"mock-{uuid.uuid4().hex}"
        return ref, f"/mock-gateway/pay?ref={ref}&amount={amount}"

    def verify(self, *, payload: dict) -> tuple[bool, dict]:
        return payload.get("result") == "success", payload


_MOCK = MockGateway()


def get_gateway() -> PaymentGateway:
    if settings.PAYMENT_GATEWAY != "mock":
        raise RuntimeError(f"unknown PAYMENT_GATEWAY={settings.PAYMENT_GATEWAY}")
    return _MOCK
