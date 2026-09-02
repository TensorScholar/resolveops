from resolveops.adapters.actions import MockActionExecutor
from resolveops.domain.models import (
    ActionExecution,
    ActionKind,
    ActionProposal,
    Approval,
    ExecutionState,
    ReviewState,
)


def approval(state: ReviewState) -> Approval:
    return Approval(
        analysis_id="a",
        reviewer="r",
        state=state,
    )


def test_executor_rejects_unapproved() -> None:
    result = MockActionExecutor().execute(
        ActionProposal(
            kind=ActionKind.CANCELLATION,
            resource_id="c",
            reason="test",
        ),
        approval=approval(ReviewState.REJECTED),
        idempotency_key="ro_rejected",
    )
    assert result.state is ExecutionState.FAILED
    assert result.external_reference is None
    assert "requires" in result.message


def test_executor_plan_change() -> None:
    result = MockActionExecutor().execute(
        ActionProposal(
            kind=ActionKind.PLAN_CHANGE,
            resource_id="c",
            target_plan="pro",
            reason="test",
        ),
        approval=approval(ReviewState.APPROVED),
        idempotency_key="ro_plan_change",
    )
    assert result.state is ExecutionState.SUCCEEDED
    assert result.external_reference and result.external_reference.startswith("plan_")


def test_executor_cancel() -> None:
    result = MockActionExecutor().execute(
        ActionProposal(
            kind=ActionKind.CANCELLATION,
            resource_id="c",
            reason="test",
        ),
        approval=approval(ReviewState.APPROVED),
        idempotency_key="ro_cancel",
    )
    assert result.state is ExecutionState.SUCCEEDED
    assert result.external_reference and result.external_reference.startswith("cancel_")


def test_executor_rejects_ambiguous_actions() -> None:
    refund = MockActionExecutor().execute(
        ActionProposal(
            kind=ActionKind.REFUND,
            resource_id="c",
            reason="test",
        ),
        approval=approval(ReviewState.APPROVED),
        idempotency_key="ro_refund",
    )
    plan = MockActionExecutor().execute(
        ActionProposal(
            kind=ActionKind.PLAN_CHANGE,
            resource_id="c",
            reason="test",
        ),
        approval=approval(ReviewState.APPROVED),
        idempotency_key="ro_plan",
    )
    assert refund.state is ExecutionState.FAILED and refund.external_reference is None
    assert plan.state is ExecutionState.FAILED and plan.external_reference is None


def test_mock_reconciliation_reuses_stable_idempotency_key() -> None:
    action = ActionProposal(
        kind=ActionKind.REFUND,
        resource_id="c",
        amount=10,
        reason="test",
    )
    approved = approval(ReviewState.APPROVED)
    first = MockActionExecutor().execute(
        action,
        approval=approved,
        idempotency_key="ro_stable",
    )
    pending = ActionExecution(
        analysis_id=approved.analysis_id,
        approval_id=approved.id,
        action=action,
        idempotency_key="ro_stable",
    )
    reconciled = MockActionExecutor().reconcile(pending)
    assert first.external_reference == reconciled.external_reference
