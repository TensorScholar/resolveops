"""Offline demonstration."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from resolveops.bootstrap import build_service
from resolveops.domain.models import (
    CustomerProfile,
    ExecutionState,
    KnowledgeArticle,
    Outcome,
    PaymentSnapshot,
    Ticket,
)


def run_demo(database: str | None = None) -> dict[str, object]:
    payment = PaymentSnapshot(
        id="pay_demo_duplicate_charge",
        customer_id="cust_demo",
        amount=Decimal("49.00"),
        amount_refunded=Decimal("0.00"),
        currency="usd",
        refundable=True,
        status="succeeded",
    )
    service = build_service(database, payments=(payment,))
    service.seed_customer(
        CustomerProfile(
            id="cust_demo",
            plan="pro",
            lifetime_value=Decimal("1800"),
            account_age_days=420,
        )
    )
    service.seed_article(
        KnowledgeArticle(
            id="kb_refund",
            title="Refund policy",
            body=(
                "Refunds up to $250 may be considered within 30 days. "
                "A human reviewer must approve any refund action."
            ),
            source_uri="kb://billing/refunds",
            owner="support-operations",
            updated_at=datetime.now(UTC),
        )
    )
    ticket = Ticket(
        customer_id="cust_demo",
        message="I was charged twice. Please refund $49.00.",
        payment_reference=payment.id,
    )
    analysis = service.analyze(ticket)
    approval, execution = service.review(
        analysis.id,
        reviewer="demo.manager@example.com",
        approve=True,
        note="Duplicate charge verified in the demo fixture.",
    )
    service.record_outcome(
        Outcome(
            ticket_id=ticket.id,
            resolved=bool(execution and execution.state is ExecutionState.SUCCEEDED),
            escalated=False,
            human_minutes=2,
            csat=5,
            model_cost_usd=Decimal("0.0132"),
        )
    )
    service.verify_audit()
    return {
        "ticket": ticket.model_dump(mode="json"),
        "analysis": analysis.model_dump(mode="json"),
        "approval": approval.model_dump(mode="json"),
        "execution": execution.model_dump(mode="json") if execution else None,
        "metrics": service.metrics(),
        "audit_events": len(service.store.list_audit()),
    }
