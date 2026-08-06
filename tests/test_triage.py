from decimal import Decimal

import pytest

from resolveops.domain.models import ActionKind, IntentKind, Ticket
from resolveops.domain.triage import classify_intent, propose_action


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Please refund $12", IntentKind.REFUND),
        ("I want to upgrade my plan", IntentKind.PLAN_CHANGE),
        ("Cancel my subscription", IntentKind.CANCELLATION),
        ("I am locked out", IntentKind.ACCOUNT_ACCESS),
        ("How does billing work?", IntentKind.INFORMATION),
        ("Do something", IntentKind.UNKNOWN),
    ],
)
def test_classify_intent(message: str, expected: IntentKind) -> None:
    assert classify_intent(message) is expected


def test_refund_action_extracts_money() -> None:
    ticket = Ticket(customer_id="c1", message="Refund USD 49.95 please")
    action = propose_action(ticket, IntentKind.REFUND)
    assert action is not None
    assert action.kind is ActionKind.REFUND
    assert action.amount == Decimal("49.95")


def test_refund_does_not_treat_unmarked_number_as_money() -> None:
    action = propose_action(
        Ticket(customer_id="c1", message="Refund order 12345"),
        IntentKind.REFUND,
    )
    assert action is not None
    assert action.amount is None
