"""Deterministic billing system-of-record adapter for tests and local demos."""

from __future__ import annotations

from collections.abc import Iterable

from resolveops.domain.models import PaymentSnapshot


class MemoryBillingReader:
    """Expose explicit payment lookup without customer-level search heuristics."""

    def __init__(self, payments: Iterable[PaymentSnapshot] = ()) -> None:
        self._payments = {payment.id: payment for payment in payments}

    def get_payment(self, payment_id: str) -> PaymentSnapshot | None:
        return self._payments.get(payment_id)

    def put_payment(self, payment: PaymentSnapshot) -> None:
        """Replace a fixture snapshot to simulate system-of-record state changes."""
        self._payments[payment.id] = payment

    def remove_payment(self, payment_id: str) -> None:
        """Remove a fixture snapshot to simulate a missing system-of-record resource."""
        self._payments.pop(payment_id, None)
