from datetime import UTC, datetime, timedelta
from decimal import Decimal

from resolveops.domain.models import (
    ActionKind,
    ActionProposal,
    Citation,
    Disposition,
    PolicySettings,
)
from resolveops.domain.policy import evaluate


def citation(age_days: int = 0) -> Citation:
    return Citation(
        article_id="a",
        title="A",
        source_uri="kb://a",
        excerpt="Policy",
        score=0.9,
        updated_at=datetime.now(UTC) - timedelta(days=age_days),
    )


def refund(amount: Decimal | None) -> ActionProposal:
    return ActionProposal(
        kind=ActionKind.REFUND,
        resource_id="c",
        amount=amount,
        reason="test",
    )


def test_information_with_evidence_can_respond() -> None:
    decision = evaluate(
        confidence=0.9,
        citations=(citation(),),
        action=None,
        settings=PolicySettings(),
    )
    assert decision.disposition is Disposition.RESPOND


def test_missing_evidence_escalates() -> None:
    decision = evaluate(
        confidence=0.9,
        citations=(),
        action=None,
        settings=PolicySettings(),
    )
    assert decision.disposition is Disposition.ESCALATE


def test_refund_requires_review() -> None:
    decision = evaluate(
        confidence=0.9,
        citations=(citation(),),
        action=refund(Decimal("49")),
        settings=PolicySettings(),
    )
    assert decision.disposition is Disposition.REVIEW_REQUIRED
    assert decision.action_allowed


def test_oversized_refund_denied() -> None:
    decision = evaluate(
        confidence=0.9,
        citations=(citation(),),
        action=refund(Decimal("999")),
        settings=PolicySettings(),
    )
    assert decision.disposition is Disposition.DENY


def test_unknown_refund_amount_requires_review() -> None:
    decision = evaluate(
        confidence=0.9,
        citations=(citation(),),
        action=refund(None),
        settings=PolicySettings(),
    )
    assert decision.disposition is Disposition.REVIEW_REQUIRED


def test_stale_evidence_escalates() -> None:
    decision = evaluate(
        confidence=0.9,
        citations=(citation(365),),
        action=None,
        settings=PolicySettings(maximum_article_age_days=30),
    )
    assert decision.disposition is Disposition.ESCALATE
