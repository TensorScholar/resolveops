"""Deterministic intent and action extraction."""

from __future__ import annotations

import re
from decimal import Decimal

from resolveops.domain.models import ActionKind, ActionProposal, IntentKind, Ticket

_MONEY = re.compile(
    r"(?:(?P<symbol>\$)\s*|(?P<code>usd)\s+)(?P<amount>\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)


def classify_intent(message: str) -> IntentKind:
    text = message.casefold()
    if ("policy" in text or "how" in text or "what" in text) and any(
        word in text for word in ("refund", "billing", "plan", "subscription")
    ):
        return IntentKind.INFORMATION
    if any(word in text for word in ("refund", "money back", "charged twice", "reimburse")):
        return IntentKind.REFUND
    if any(word in text for word in ("upgrade", "downgrade", "change plan", "switch plan")):
        return IntentKind.PLAN_CHANGE
    if any(word in text for word in ("cancel", "close subscription", "terminate subscription")):
        return IntentKind.CANCELLATION
    if any(word in text for word in ("login", "password", "locked out", "account access")):
        return IntentKind.ACCOUNT_ACCESS
    if any(word in text for word in ("how", "what", "where", "when", "policy", "explain")):
        return IntentKind.INFORMATION
    return IntentKind.UNKNOWN


def extract_refund_request(message: str) -> tuple[Decimal | None, str | None]:
    """Extract one unambiguous explicit USD amount; never guess among distinct values."""
    matches = list(_MONEY.finditer(message))
    if not matches:
        return None, None

    amounts = {
        Decimal(match.group("amount")).quantize(Decimal("0.01")) for match in matches
    }
    if len(amounts) != 1:
        return None, "usd"
    return next(iter(amounts)), "usd"


def propose_action(ticket: Ticket, intent: IntentKind) -> ActionProposal | None:
    if intent is IntentKind.REFUND:
        # A refund cannot be proposed safely from customer text alone. The application
        # binds it to a verified payment snapshot from the billing system of record.
        return None
    if intent is IntentKind.PLAN_CHANGE:
        text = ticket.message.casefold()
        target = "pro" if "upgrade" in text else "basic" if "downgrade" in text else None
        return ActionProposal(
            kind=ActionKind.PLAN_CHANGE,
            resource_id=ticket.customer_id,
            target_plan=target,
            reason="Customer requested a plan change.",
        )
    if intent is IntentKind.CANCELLATION:
        return ActionProposal(
            kind=ActionKind.CANCELLATION,
            resource_id=ticket.customer_id,
            reason="Customer requested cancellation.",
        )
    return None
