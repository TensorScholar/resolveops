from decimal import Decimal

import pytest

from resolveops.domain.errors import InvalidTransitionError, PolicyDeniedError
from resolveops.domain.models import (
    ActionResourceKind,
    Disposition,
    ExecutionState,
    Outcome,
    Ticket,
)


def refund_ticket(message: str, *, ticket_id: str | None = None) -> Ticket:
    data: dict[str, object] = {
        "customer_id": "cust_1",
        "message": message,
        "payment_reference": "pay_cust_1",
    }
    if ticket_id is not None:
        data["id"] = ticket_id
    return Ticket.model_validate(data)


def test_analyze_refund(service) -> None:
    analysis = service.analyze(refund_ticket("I was charged twice, refund $49"))
    assert analysis.intent.value == "refund"
    assert analysis.disposition is Disposition.REVIEW_REQUIRED
    assert analysis.citations
    assert analysis.proposed_action is not None
    assert analysis.proposed_action.resource_kind is ActionResourceKind.PAYMENT
    assert analysis.proposed_action.resource_id == "pay_cust_1"
    assert analysis.proposed_action.currency == "usd"
    assert analysis.proposed_action.resource_hash is not None


def test_approve_and_execute(service) -> None:
    analysis = service.analyze(refund_ticket("I was charged twice, refund $49"))
    approval, execution = service.review(
        analysis.id,
        reviewer="manager@example.com",
        approve=True,
    )
    assert approval.state.value == "approved"
    assert execution is not None and execution.state is ExecutionState.SUCCEEDED
    assert execution.attempt_count == 1
    assert execution.idempotency_key.startswith("ro_")
    assert execution.action.resource_id == "pay_cust_1"


def test_reject_does_not_execute(service) -> None:
    analysis = service.analyze(refund_ticket("I was charged twice, refund $49"))
    _, execution = service.review(
        analysis.id,
        reviewer="manager@example.com",
        approve=False,
    )
    assert execution is None


def test_rejection_remains_possible_after_evidence_becomes_stale(service) -> None:
    analysis = service.analyze(refund_ticket("Refund $49"))
    service.store.articles.clear()
    approval, execution = service.review(
        analysis.id,
        reviewer="manager@example.com",
        approve=False,
    )
    assert approval.state.value == "rejected"
    assert execution is None


def test_cannot_review_information_response(service) -> None:
    analysis = service.analyze(Ticket(customer_id="cust_1", message="What is the refund policy?"))
    with pytest.raises(InvalidTransitionError):
        service.review(analysis.id, reviewer="manager@example.com", approve=True)


def test_denied_refund_cannot_be_approved(service) -> None:
    analysis = service.analyze(refund_ticket("Refund $999"))
    assert analysis.disposition is Disposition.DENY
    assert "refund_exceeds_policy_limit" in analysis.disposition_reasons
    with pytest.raises(PolicyDeniedError):
        service.review(analysis.id, reviewer="manager@example.com", approve=True)


def test_unknown_refund_amount_cannot_be_approved(service) -> None:
    analysis = service.analyze(refund_ticket("Refund me"))
    with pytest.raises(PolicyDeniedError, match="refund_amount_unknown"):
        service.review(analysis.id, reviewer="manager@example.com", approve=True)
    assert service.store.list_executions() == []


def test_distinct_refund_amounts_cannot_be_approved(service) -> None:
    analysis = service.analyze(refund_ticket("Charged $100; please refund $20"))
    assert analysis.proposed_action is not None
    assert analysis.proposed_action.amount is None
    with pytest.raises(PolicyDeniedError, match="refund_amount_unknown"):
        service.review(analysis.id, reviewer="manager@example.com", approve=True)
    assert service.store.list_executions() == []


def test_missing_evidence_action_cannot_be_approved(service) -> None:
    analysis = service.analyze(refund_ticket("Refund $49"))
    assert analysis.disposition is Disposition.REVIEW_REQUIRED
    service.store.articles.clear()
    with pytest.raises(PolicyDeniedError, match="insufficient_current_evidence"):
        service.review(analysis.id, reviewer="manager@example.com", approve=True)
    assert service.store.list_executions() == []


def test_review_cannot_be_replayed(service) -> None:
    analysis = service.analyze(refund_ticket("I was charged twice, refund $49"))
    service.review(analysis.id, reviewer="manager@example.com", approve=True)
    with pytest.raises(InvalidTransitionError, match="already been reviewed"):
        service.review(analysis.id, reviewer="other@example.com", approve=True)
    assert len(service.store.list_executions()) == 1


def test_metrics_are_outcome_based(service) -> None:
    ticket = Ticket(customer_id="cust_1", message="What is the refund policy?")
    service.analyze(ticket)
    service.record_outcome(
        Outcome(
            ticket_id=ticket.id,
            resolved=True,
            escalated=False,
            model_cost_usd=Decimal("0.01"),
        )
    )
    metrics = service.metrics()
    assert metrics["resolution_rate"] == 1.0
    assert metrics["cost_per_resolved_outcome_usd"] == "0.0100"
