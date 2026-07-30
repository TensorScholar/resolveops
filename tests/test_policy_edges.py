from decimal import Decimal

from resolveops.domain.models import (
    ActionKind,
    ActionProposal,
    Citation,
    Disposition,
    PolicySettings,
)
from resolveops.domain.policy import evaluate
from datetime import UTC, datetime


def cite() -> tuple[Citation, ...]:
    return (
        Citation(
            article_id="a",
            title="a",
            source_uri="a",
            excerpt="a",
            score=1,
            updated_at=datetime.now(UTC),
        ),
    )


def test_disallowed_action_denied() -> None:
    action = ActionProposal(
        kind=ActionKind.CANCELLATION,
        resource_id="c",
        reason="r",
    )
    decision = evaluate(
        confidence=1,
        citations=cite(),
        action=action,
        settings=PolicySettings(allowed_actions=frozenset({ActionKind.REFUND})),
    )
    assert decision.disposition is Disposition.DENY


def test_automatic_low_refund() -> None:
    action = ActionProposal(
        kind=ActionKind.REFUND,
        resource_id="c",
        amount=Decimal("5"),
        reason="r",
    )
    decision = evaluate(
        confidence=1,
        citations=cite(),
        action=action,
        settings=PolicySettings(
            action_requires_approval=False,
            auto_refund_limit=Decimal("10"),
        ),
    )
    assert decision.disposition is Disposition.RESPOND
    assert decision.action_allowed


def test_refund_above_auto_limit_requires_review() -> None:
    action = ActionProposal(
        kind=ActionKind.REFUND,
        resource_id="c",
        amount=Decimal("20"),
        reason="r",
    )
    decision = evaluate(
        confidence=1,
        citations=cite(),
        action=action,
        settings=PolicySettings(
            action_requires_approval=False,
            auto_refund_limit=Decimal("10"),
        ),
    )
    assert decision.disposition is Disposition.REVIEW_REQUIRED
