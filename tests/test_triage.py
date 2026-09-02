from decimal import Decimal

import pytest

from resolveops.domain.models import IntentKind, Ticket
from resolveops.domain.triage import classify_intent, extract_refund_request, propose_action


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


def test_refund_request_extracts_money() -> None:
    amount, currency = extract_refund_request("Refund USD 49.95 please")
    assert amount == Decimal("49.95")
    assert currency == "usd"


def test_refund_does_not_treat_unmarked_number_as_money() -> None:
    assert extract_refund_request("Refund order 12345") == (None, None)


def test_triage_cannot_create_customer_targeted_refund_action() -> None:
    ticket = Ticket(customer_id="c1", message="Refund $49.95")
    assert propose_action(ticket, IntentKind.REFUND) is None
