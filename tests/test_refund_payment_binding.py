from __future__ import annotations

from decimal import Decimal

import pytest

from resolveops.adapters.actions import MockActionExecutor
from resolveops.adapters.billing import MemoryBillingReader
from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.memory import MemoryStore
from resolveops.application.service import ResolveOpsService
from resolveops.domain.audit import object_digest
from resolveops.domain.errors import InvalidTransitionError, PolicyDeniedError
from resolveops.domain.models import (
    ActionResourceKind,
    CustomerProfile,
    Disposition,
    KnowledgeArticle,
    PaymentSnapshot,
    Ticket,
)


def build_service(*payments: PaymentSnapshot) -> tuple[ResolveOpsService, MemoryBillingReader]:
    billing = MemoryBillingReader(payments)
    service = ResolveOpsService(
        store=MemoryStore(),
        generator=DeterministicResponseGenerator(),
        action_executor=MockActionExecutor(),
        billing_reader=billing,
    )
    service.seed_customer(CustomerProfile(id="cust"))
    service.seed_customer(CustomerProfile(id="other"))
    service.seed_article(
        KnowledgeArticle(
            id="kb_refund",
            title="Refund policy",
            body="Refunds up to $250 require human approval.",
            source_uri="kb://refund",
            owner="support",
        )
    )
    return service, billing


def payment(
    *,
    payment_id: str = "pay_1",
    customer_id: str = "cust",
    amount: str = "100.00",
    amount_refunded: str = "0.00",
    currency: str = "usd",
    refundable: bool = True,
    status: str = "succeeded",
) -> PaymentSnapshot:
    return PaymentSnapshot(
        id=payment_id,
        customer_id=customer_id,
        amount=Decimal(amount),
        amount_refunded=Decimal(amount_refunded),
        currency=currency,
        refundable=refundable,
        status=status,
    )


def refund_ticket(
    message: str = "Refund $40",
    *,
    payment_reference: str | None = "pay_1",
    ticket_id: str | None = None,
) -> Ticket:
    data: dict[str, object] = {
        "customer_id": "cust",
        "message": message,
        "payment_reference": payment_reference,
    }
    if ticket_id is not None:
        data["id"] = ticket_id
    return Ticket.model_validate(data)


def test_refund_without_explicit_payment_reference_escalates() -> None:
    service, _ = build_service(payment())
    analysis = service.analyze(refund_ticket(payment_reference=None))

    assert analysis.disposition is Disposition.ESCALATE
    assert analysis.proposed_action is None
    assert "refund_payment_target_missing" in analysis.disposition_reasons


def test_unknown_payment_reference_escalates() -> None:
    service, _ = build_service(payment())
    analysis = service.analyze(refund_ticket(payment_reference="pay_missing"))

    assert analysis.disposition is Disposition.ESCALATE
    assert analysis.proposed_action is None
    assert "refund_payment_target_not_found" in analysis.disposition_reasons


def test_payment_owned_by_another_customer_is_denied() -> None:
    service, _ = build_service(payment(customer_id="other"))
    analysis = service.analyze(refund_ticket())

    assert analysis.disposition is Disposition.DENY
    assert analysis.proposed_action is None
    assert "refund_payment_ownership_mismatch" in analysis.disposition_reasons


@pytest.mark.parametrize(
    "snapshot",
    [
        payment(refundable=False),
        payment(amount="100.00", amount_refunded="100.00"),
    ],
)
def test_nonrefundable_payment_is_denied(snapshot: PaymentSnapshot) -> None:
    service, _ = build_service(snapshot)
    analysis = service.analyze(refund_ticket())

    assert analysis.disposition is Disposition.DENY
    assert analysis.proposed_action is None
    assert "refund_payment_not_refundable" in analysis.disposition_reasons


def test_currency_mismatch_is_denied() -> None:
    service, _ = build_service(payment(currency="eur"))
    analysis = service.analyze(refund_ticket("Refund $40"))

    assert analysis.disposition is Disposition.DENY
    assert analysis.proposed_action is None
    assert "refund_currency_mismatch" in analysis.disposition_reasons


def test_requested_refund_cannot_exceed_remaining_payment_amount() -> None:
    service, _ = build_service(payment(amount="100.00", amount_refunded="70.00"))
    analysis = service.analyze(refund_ticket("Refund $40"))

    assert analysis.disposition is Disposition.DENY
    assert analysis.proposed_action is None
    assert "refund_exceeds_remaining_payment_amount" in analysis.disposition_reasons


def test_valid_refund_is_bound_to_exact_payment_snapshot() -> None:
    snapshot = payment(amount="100.00", amount_refunded="20.00")
    service, _ = build_service(snapshot)
    analysis = service.analyze(refund_ticket("Refund $40"))

    assert analysis.disposition is Disposition.REVIEW_REQUIRED
    action = analysis.proposed_action
    assert action is not None
    assert action.resource_kind is ActionResourceKind.PAYMENT
    assert action.resource_id == snapshot.id
    assert action.resource_hash == object_digest(snapshot.model_dump(mode="json"))
    assert action.amount == Decimal("40.00")
    assert action.currency == "usd"


def test_explicit_reference_selects_exact_payment_without_customer_search() -> None:
    first = payment(payment_id="pay_a", amount="80.00")
    second = payment(payment_id="pay_b", amount="80.00")
    service, _ = build_service(first, second)

    analysis = service.analyze(
        refund_ticket("Refund $40", payment_reference="pay_b")
    )

    assert analysis.proposed_action is not None
    assert analysis.proposed_action.resource_id == "pay_b"
    assert analysis.proposed_action.resource_hash == object_digest(
        second.model_dump(mode="json")
    )


def test_payment_state_change_before_approval_fails_closed() -> None:
    original = payment(amount="100.00")
    service, billing = build_service(original)
    analysis = service.analyze(refund_ticket("Refund $40"))
    billing.put_payment(original.model_copy(update={"amount_refunded": Decimal("20.00")}))

    with pytest.raises(PolicyDeniedError, match="state changed"):
        service.review(analysis.id, reviewer="manager@example.com", approve=True)

    assert service.store.list_executions() == []


def test_payment_ownership_change_before_approval_fails_closed() -> None:
    original = payment()
    service, billing = build_service(original)
    analysis = service.analyze(refund_ticket())
    billing.put_payment(original.model_copy(update={"customer_id": "other"}))

    with pytest.raises(PolicyDeniedError, match="ownership changed"):
        service.review(analysis.id, reviewer="manager@example.com", approve=True)

    assert service.store.list_executions() == []


def test_payment_disappearing_before_approval_fails_closed() -> None:
    original = payment()
    service, billing = build_service(original)
    analysis = service.analyze(refund_ticket())
    billing._payments.clear()

    with pytest.raises(PolicyDeniedError, match="no longer available"):
        service.review(analysis.id, reviewer="manager@example.com", approve=True)

    assert service.store.list_executions() == []


def test_exact_case_replay_remains_canonical_but_approval_revalidates_payment() -> None:
    original = payment(amount="100.00")
    service, billing = build_service(original)
    ticket = refund_ticket("Refund $40", ticket_id="case-stable")
    first = service.analyze(ticket)

    billing.put_payment(original.model_copy(update={"amount_refunded": Decimal("70.00")}))
    replayed = service.analyze(Ticket.model_validate(ticket.model_dump()))

    assert replayed == first
    assert len(service.store.list_analyses()) == 1
    with pytest.raises(PolicyDeniedError, match="state changed"):
        service.review(first.id, reviewer="manager@example.com", approve=True)
    assert service.store.list_executions() == []


def test_changed_payment_reference_on_same_ticket_id_is_integrity_conflict() -> None:
    first_payment = payment(payment_id="pay_a")
    second_payment = payment(payment_id="pay_b")
    service, _ = build_service(first_payment, second_payment)
    ticket = refund_ticket(payment_reference="pay_a", ticket_id="case-payment-ref")
    service.analyze(ticket)

    changed = ticket.model_copy(update={"payment_reference": "pay_b"})
    with pytest.raises(Exception, match="different content"):
        service.analyze(changed)


def test_missing_target_analysis_has_no_action_to_review() -> None:
    service, _ = build_service(payment())
    analysis = service.analyze(refund_ticket(payment_reference=None))

    with pytest.raises(InvalidTransitionError, match="no action"):
        service.review(analysis.id, reviewer="manager@example.com", approve=True)
