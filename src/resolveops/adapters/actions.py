"""Mock business action adapter."""

from __future__ import annotations

from resolveops.domain.models import ActionKind, ActionProposal, Approval, ReviewState


class MockActionExecutor:
    def execute(
        self, action: ActionProposal, *, approval: Approval
    ) -> tuple[bool, str, str | None]:
        if approval.state is not ReviewState.APPROVED:
            return False, "Action requires an approved review.", None
        if action.kind is ActionKind.REFUND:
            amount = f"${action.amount}" if action.amount is not None else "an unspecified amount"
            return True, f"Mock refund of {amount} completed.", f"refund_{approval.id}"
        if action.kind is ActionKind.PLAN_CHANGE:
            return (
                True,
                f"Mock plan change to {action.target_plan} completed.",
                f"plan_{approval.id}",
            )
        if action.kind is ActionKind.CANCELLATION:
            return True, "Mock cancellation completed.", f"cancel_{approval.id}"
        return False, "Unsupported action.", None
