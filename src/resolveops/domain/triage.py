"""Deterministic intent and action extraction."""

from __future__ import annotations

import re
from decimal import Decimal

from resolveops.domain.models import ActionKind, ActionProposal, IntentKind, Ticket

_MONEY = re.compile(r"(?:\$\s*|usd\s+)(\d+(?:\.\d{1,2})?)", re.IGNORECASE)


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


def _extract_amount(message: str) -> Decimal | None:
    match = _MONEY.search(message)
    return Decimal(match.group(1)).quantize(Decimal("0.01")) if match else None


def propose_action(ticket: Ticket, intent: IntentKind) -> ActionProposal | None:
    if intent is IntentKind.REFUND:
        return ActionProposal(
            kind=ActionKind.REFUND,
            resource_id=ticket.customer_id,
            amount=_extract_amount(ticket.message),
            reason="Customer requested a refund.",
        )
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
