"""Evidence and action policy."""

from __future__ import annotations

from datetime import UTC, datetime
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

    current_citations = []
    for citation in citations:
        age = current_time - citation.updated_at
        if age.total_seconds() < 0:
            continue
        if age.days <= settings.maximum_article_age_days:
            current_citations.append(citation)
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
    if action.kind is ActionKind.PLAN_CHANGE and not action.target_plan:
        return PolicyDecision(
            disposition=Disposition.REVIEW_REQUIRED,
            reasons=("plan_target_unknown",),
            action_allowed=False,
        )
    if reasons:
        return PolicyDecision(
            disposition=Disposition.ESCALATE,
            reasons=tuple(reasons),
            action_allowed=False,
        )
    return PolicyDecision(
        disposition=Disposition.REVIEW_REQUIRED,
        reasons=("destructive_action_requires_approval",),
        action_allowed=True,
    )
