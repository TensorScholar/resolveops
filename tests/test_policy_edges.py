from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from resolveops.domain.models import (
    ActionKind,
    ActionProposal,
    Citation,
    Disposition,
    PolicySettings,
)
from resolveops.domain.policy import evaluate


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


def test_automatic_action_configuration_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PolicySettings.model_validate({"action_requires_approval": False})


def test_all_valid_actions_require_review() -> None:
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
        settings=PolicySettings(),
    )
    assert decision.disposition is Disposition.REVIEW_REQUIRED
    assert decision.action_allowed


def test_unknown_plan_target_cannot_execute() -> None:
    action = ActionProposal(
        kind=ActionKind.PLAN_CHANGE,
        resource_id="c",
        reason="r",
    )
    decision = evaluate(
        confidence=1,
        citations=cite(),
        action=action,
        settings=PolicySettings(),
    )
    assert decision.disposition is Disposition.REVIEW_REQUIRED
    assert not decision.action_allowed
    assert decision.reasons == ("plan_target_unknown",)
