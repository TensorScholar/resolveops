from datetime import datetime

import pytest
from pydantic import ValidationError

from resolveops.domain.models import (
    ActionExecution,
    ActionKind,
    ActionProposal,
    ExecutionResult,
    ExecutionState,
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
