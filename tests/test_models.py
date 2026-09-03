from datetime import datetime
from decimal import Decimal
import re

import pytest
from pydantic import ValidationError

from resolveops.domain.models import (
    ActionExecution,
    ActionKind,
    ActionProposal,
    ExecutionResult,
    ExecutionState,
    PaymentSnapshot,
    Ticket,
)


def action() -> ActionProposal:
    return ActionProposal(
        kind=ActionKind.CANCELLATION,
        resource_id="customer_1",
        reason="test",
    )


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Ticket.model_validate({"customer_id": "c", "message": "x", "unexpected": True})


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        Ticket(customer_id="c", message="x", received_at=datetime.now())


def test_action_resource_id_cannot_be_empty() -> None:
    with pytest.raises(ValidationError):
        ActionProposal(
            kind=ActionKind.REFUND,
            resource_id="",
            reason="invalid empty target",
        )


@pytest.mark.parametrize("missing", ["amount_refunded", "refundable", "status"])
def test_payment_safety_state_is_required(missing: str) -> None:
    payload: dict[str, object] = {
        "id": "pay_1",
        "customer_id": "c",
        "amount": Decimal("10.00"),
        "amount_refunded": Decimal("0.00"),
        "currency": "usd",
        "refundable": True,
        "status": "succeeded",
    }
    payload.pop(missing)

    with pytest.raises(ValidationError):
        PaymentSnapshot.model_validate(payload)


def test_payment_refund_total_cannot_exceed_payment_amount() -> None:
    with pytest.raises(ValidationError, match="amount_refunded cannot exceed amount"):
        PaymentSnapshot(
            id="pay_1",
            customer_id="c",
            amount=Decimal("10.00"),
            amount_refunded=Decimal("11.00"),
            currency="usd",
            refundable=True,
            status="succeeded",
        )


def test_payment_currency_must_be_lowercase_three_letter_code() -> None:
    with pytest.raises(ValidationError):
        PaymentSnapshot(
            id="pay_1",
            customer_id="c",
            amount=Decimal("10.00"),
            amount_refunded=Decimal("0.00"),
            currency="USD",
            refundable=True,
            status="succeeded",
        )


def test_payment_schema_rejects_negative_decimal_strings() -> None:
    schema = PaymentSnapshot.model_json_schema()
    amount_schema = schema["properties"]["amount_refunded"]
    string_variant = next(
        item for item in amount_schema["anyOf"] if item.get("type") == "string"
    )
    pattern = string_variant["pattern"]
    assert re.fullmatch(pattern, "1.00") is not None
    assert re.fullmatch(pattern, "-1.00") is None


def test_payment_remaining_refundable_is_exact_decimal() -> None:
    snapshot = PaymentSnapshot(
        id="pay_1",
        customer_id="c",
        amount=Decimal("10.00"),
        amount_refunded=Decimal("3.25"),
        currency="usd",
        refundable=True,
        status="succeeded",
    )
    assert snapshot.remaining_refundable == Decimal("6.75")


def test_pending_execution_cannot_claim_provider_attempt() -> None:
    with pytest.raises(ValidationError, match="pending execution cannot have provider attempts"):
        ActionExecution(
            analysis_id="analysis_1",
            approval_id="approval_1",
            action=action(),
            idempotency_key="ro_test",
            attempt_count=1,
        )


@pytest.mark.parametrize("state", [ExecutionState.PENDING, ExecutionState.IN_FLIGHT])
def test_provider_result_cannot_return_internal_state(state: ExecutionState) -> None:
    with pytest.raises(ValidationError, match="provider result cannot use an internal"):
        ExecutionResult(
            state=state,
            message="invalid provider state",
        )


def test_succeeded_result_requires_provider_reference() -> None:
    with pytest.raises(ValidationError, match="requires external reference"):
        ExecutionResult(
            state=ExecutionState.SUCCEEDED,
            message="provider reported success without evidence",
        )
