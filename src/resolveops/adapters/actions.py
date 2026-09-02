"""Mock business action adapter."""

from __future__ import annotations

from resolveops.domain.models import (
    ActionExecution,
    ActionKind,
    ActionProposal,
    Approval,
    ExecutionResult,
    ExecutionState,
    ReviewState,
)


class MockActionExecutor:
    def execute(
        self,
        action: ActionProposal,
        *,
        approval: Approval,
        idempotency_key: str,
    ) -> ExecutionResult:
        if approval.state is not ReviewState.APPROVED:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                message="Action requires an approved review.",
            )
        reference_suffix = idempotency_key.removeprefix("ro_")[:24]
        if action.kind is ActionKind.REFUND:
            if action.amount is None:
                return ExecutionResult(
                    state=ExecutionState.FAILED,
                    message="Refund amount is required.",
                )
            amount = f"${action.amount}"
            return ExecutionResult(
                state=ExecutionState.SUCCEEDED,
                message=f"Mock refund of {amount} completed.",
                external_reference=f"refund_{reference_suffix}",
                provider_status="succeeded",
            )
        if action.kind is ActionKind.PLAN_CHANGE:
            if not action.target_plan:
                return ExecutionResult(
                    state=ExecutionState.FAILED,
                    message="Target plan is required.",
                )
            return ExecutionResult(
                state=ExecutionState.SUCCEEDED,
                message=f"Mock plan change to {action.target_plan} completed.",
                external_reference=f"plan_{reference_suffix}",
                provider_status="succeeded",
            )
        if action.kind is ActionKind.CANCELLATION:
            return ExecutionResult(
                state=ExecutionState.SUCCEEDED,
                message="Mock cancellation completed.",
                external_reference=f"cancel_{reference_suffix}",
                provider_status="succeeded",
            )
        return ExecutionResult(
            state=ExecutionState.FAILED,
            message="Unsupported action.",
        )

    def reconcile(self, execution: ActionExecution) -> ExecutionResult:
        """Resolve the mock operation using the same stable idempotency key."""
        synthetic_approval = Approval(
            id=execution.approval_id,
            analysis_id=execution.analysis_id,
            reviewer="mock-reconciliation",
            state=ReviewState.APPROVED,
        )
        return self.execute(
            execution.action,
            approval=synthetic_approval,
            idempotency_key=execution.idempotency_key,
        )
