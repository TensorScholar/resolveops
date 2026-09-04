"""Safe mapping from a live Stripe charge to ResolveOps customer/ticket."""

from __future__ import annotations

from resolveops.application.service import ResolveOpsService
from resolveops.domain.errors import IntegrityError
from resolveops.domain.models import CustomerProfile, PaymentSnapshot, Ticket


def seed_customer_for_payment(
    service: ResolveOpsService, payment: PaymentSnapshot
) -> CustomerProfile:
    """Ensure the local customer mirrors the charge owner; never overwrite."""
    if not payment.id.startswith("ch_"):
        raise ValueError("payment must be a Stripe charge")
    if not payment.customer_id.strip():
        raise ValueError("payment customer must not be empty")
    existing = service.store.get_customer(payment.customer_id)
    if existing is not None:
        if existing.id != payment.customer_id:
            raise IntegrityError("customer claim does not match payment owner")
        return existing
    profile = CustomerProfile(id=payment.customer_id)
    service.seed_customer(profile)
    return profile


def make_ticket_for_charge(
    *,
    payment: PaymentSnapshot,
    ticket_customer_id: str,
    message: str,
    ticket_id: str | None = None,
) -> Ticket:
    """Build a ticket bound to one charge; fail closed on ownership mismatch."""
    if ticket_customer_id != payment.customer_id:
        raise IntegrityError("ticket customer does not own the charge")
    if not payment.id.startswith("ch_"):
        raise ValueError("payment must be a Stripe charge")
    if ticket_id is not None:
        return Ticket(
            id=ticket_id,
            customer_id=ticket_customer_id,
            message=message,
            payment_reference=payment.id,
        )
    return Ticket(
        customer_id=ticket_customer_id,
        message=message,
        payment_reference=payment.id,
    )
