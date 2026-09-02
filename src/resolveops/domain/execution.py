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


def apply_execution_result(
    execution: ActionExecution,
    result: ExecutionResult,
    *,
    now: datetime | None = None,
) -> ActionExecution:
    if execution.state.terminal:
        raise InvalidTransitionError("terminal execution cannot be updated")
    if result.state is ExecutionState.PENDING:
        raise IntegrityError("executor returned reserved internal state: pending")
    return ActionExecution(
        id=execution.id,
        analysis_id=execution.analysis_id,
        approval_id=execution.approval_id,
        action=execution.action,
        idempotency_key=execution.idempotency_key,
        state=result.state,
        attempt_count=execution.attempt_count + 1,
        external_reference=result.external_reference,
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
    if updated.attempt_count != current.attempt_count + 1:
        raise InvalidTransitionError("execution update lost its attempt ordering")
    if updated.updated_at < current.updated_at:
        raise IntegrityError("execution update moved time backwards")
