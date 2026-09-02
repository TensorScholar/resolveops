"""Execution lifecycle invariants."""

from __future__ import annotations

from datetime import datetime

from resolveops.domain.audit import object_digest
from resolveops.domain.errors import IntegrityError, InvalidTransitionError
from resolveops.domain.models import (
    ActionExecution,
    ActionProposal,
    Approval,
    ExecutionResult,
    ExecutionState,
    utc_now,
)


def build_idempotency_key(approval: Approval, action: ActionProposal) -> str:
    """Derive a stable, non-sensitive key for one approved action."""
    digest = object_digest(
        {
            "approval_id": approval.id,
            "analysis_id": approval.analysis_id,
            "action": action.model_dump(mode="json"),
        }
    )
    return f"ro_{digest}"


def begin_execution_attempt(
    execution: ActionExecution,
    *,
    now: datetime | None = None,
) -> ActionExecution:
    """Durably represent an adapter interaction before crossing the provider boundary."""
    if execution.state.terminal:
        raise InvalidTransitionError("terminal execution cannot start another attempt")
    return ActionExecution(
        id=execution.id,
        analysis_id=execution.analysis_id,
        approval_id=execution.approval_id,
        action=execution.action,
        idempotency_key=execution.idempotency_key,
        state=ExecutionState.IN_FLIGHT,
        attempt_count=execution.attempt_count + 1,
        external_reference=execution.external_reference,
        provider_status=execution.provider_status,
        message="Provider interaction started; outcome not yet recorded.",
        created_at=execution.created_at,
        updated_at=now or utc_now(),
    )


def apply_execution_result(
    execution: ActionExecution,
    result: ExecutionResult,
    *,
    now: datetime | None = None,
) -> ActionExecution:
    """Complete the currently persisted provider interaction without double-counting it."""
    if execution.state is not ExecutionState.IN_FLIGHT:
        raise InvalidTransitionError("execution has no in-flight provider attempt")
    return ActionExecution(
        id=execution.id,
        analysis_id=execution.analysis_id,
        approval_id=execution.approval_id,
        action=execution.action,
        idempotency_key=execution.idempotency_key,
        state=result.state,
        attempt_count=execution.attempt_count,
        external_reference=result.external_reference or execution.external_reference,
        provider_status=result.provider_status,
        message=result.message,
        created_at=execution.created_at,
        updated_at=now or utc_now(),
    )


def validate_execution_update(current: ActionExecution, updated: ActionExecution) -> None:
    if current.state.terminal:
        raise InvalidTransitionError("terminal execution cannot be updated")
    if updated.state is ExecutionState.PENDING:
        raise InvalidTransitionError("execution cannot transition back to pending")
    if (
        updated.id != current.id
        or updated.analysis_id != current.analysis_id
        or updated.approval_id != current.approval_id
        or updated.action != current.action
        or updated.idempotency_key != current.idempotency_key
        or updated.created_at != current.created_at
    ):
        raise IntegrityError("execution identity or approved action changed")
    if (
        current.external_reference is not None
        and updated.external_reference != current.external_reference
    ):
        raise IntegrityError("external operation reference changed")
    if updated.updated_at < current.updated_at:
        raise IntegrityError("execution update moved time backwards")

    if updated.state is ExecutionState.IN_FLIGHT:
        if updated.attempt_count != current.attempt_count + 1:
            raise InvalidTransitionError("new provider attempt lost its ordering")
        return

    if current.state is not ExecutionState.IN_FLIGHT:
        raise InvalidTransitionError("provider result requires an in-flight execution")
    if updated.attempt_count != current.attempt_count:
        raise InvalidTransitionError("provider result changed its attempt number")
