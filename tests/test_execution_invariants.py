from __future__ import annotations

import pytest

from resolveops.domain.errors import IntegrityError
from resolveops.domain.execution import (
    apply_execution_result,
    begin_execution_attempt,
    validate_execution_update,
)
from resolveops.domain.models import (
    ActionExecution,
    ActionKind,
    ActionProposal,
    ExecutionResult,
    ExecutionState,
)


def submitted_execution() -> ActionExecution:
    return ActionExecution(
        analysis_id="analysis_1",
        approval_id="approval_1",
        action=ActionProposal(
            kind=ActionKind.REFUND,
            resource_id="payment_1",
            amount=10,
            reason="duplicate charge",
        ),
        idempotency_key="ro_stable",
        state=ExecutionState.SUBMITTED,
        attempt_count=1,
        external_reference="provider_ref_1",
        provider_status="pending",
        message="Provider accepted the operation.",
    )


def test_reconciliation_cannot_replace_known_external_operation_reference() -> None:
    current = submitted_execution()
    in_flight = begin_execution_attempt(current)
    assert in_flight.external_reference == "provider_ref_1"
    assert in_flight.attempt_count == 2

    conflicting = apply_execution_result(
        in_flight,
        ExecutionResult(
            state=ExecutionState.SUCCEEDED,
            external_reference="provider_ref_2",
            provider_status="succeeded",
            message="Provider returned a different operation.",
        ),
    )

    with pytest.raises(IntegrityError, match="external operation reference changed"):
        validate_execution_update(in_flight, conflicting)


def test_reconciliation_preserves_known_reference_when_result_omits_it() -> None:
    current = submitted_execution()
    in_flight = begin_execution_attempt(current)
    updated = apply_execution_result(
        in_flight,
        ExecutionResult(
            state=ExecutionState.UNKNOWN,
            provider_status="lookup_timeout",
            message="Provider lookup timed out.",
        ),
    )

    validate_execution_update(in_flight, updated)
    assert updated.external_reference == "provider_ref_1"
    assert updated.attempt_count == 2
