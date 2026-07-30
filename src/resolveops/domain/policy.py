"""Evidence and action policy."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from resolveops.domain.models import (
    ActionKind,
    ActionProposal,
    Citation,
    Disposition,
    PolicyDecision,
    PolicySettings,
)


def evaluate(
    *,
    confidence: float,
    citations: tuple[Citation, ...],
    action: ActionProposal | None,
    settings: PolicySettings,
    now: datetime | None = None,
) -> PolicyDecision:
    current_time = now or datetime.now(UTC)
    reasons: list[str] = []

    current_citations = [
        citation
        for citation in citations
        if (current_time - citation.updated_at).days <= settings.maximum_article_age_days
    ]
    if len(current_citations) < settings.minimum_citations:
        reasons.append("insufficient_current_evidence")
    if confidence < settings.minimum_confidence:
        reasons.append("low_confidence")

    if action is None:
        if reasons:
            return PolicyDecision(
                disposition=Disposition.ESCALATE,
                reasons=tuple(reasons),
                action_allowed=False,
            )
        return PolicyDecision(
            disposition=Disposition.RESPOND,
            reasons=("evidence_threshold_met",),
            action_allowed=False,
        )

    if action.kind not in settings.allowed_actions:
        return PolicyDecision(
            disposition=Disposition.DENY,
            reasons=("action_not_allowed",),
            action_allowed=False,
        )
    if action.kind is ActionKind.REFUND:
        if action.amount is None:
            return PolicyDecision(
                disposition=Disposition.REVIEW_REQUIRED,
                reasons=("refund_amount_unknown",),
                action_allowed=False,
            )
        if action.amount > settings.maximum_refund:
            return PolicyDecision(
                disposition=Disposition.DENY,
                reasons=("refund_exceeds_policy_limit",),
                action_allowed=False,
            )
    if reasons:
        return PolicyDecision(
            disposition=Disposition.ESCALATE,
            reasons=tuple(reasons),
            action_allowed=False,
        )
    if settings.action_requires_approval:
        return PolicyDecision(
            disposition=Disposition.REVIEW_REQUIRED,
            reasons=("destructive_action_requires_approval",),
            action_allowed=True,
        )
    if action.kind is ActionKind.REFUND and action.amount is not None:
        if action.amount > Decimal(settings.auto_refund_limit):
            return PolicyDecision(
                disposition=Disposition.REVIEW_REQUIRED,
                reasons=("refund_exceeds_auto_limit",),
                action_allowed=True,
            )
    return PolicyDecision(
        disposition=Disposition.RESPOND,
        reasons=("policy_allows_automatic_action",),
        action_allowed=True,
    )
