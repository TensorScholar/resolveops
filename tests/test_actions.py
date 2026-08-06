from resolveops.adapters.actions import MockActionExecutor
from resolveops.domain.models import (
    ActionKind,
    ActionProposal,
    Approval,
    ReviewState,
)


def approval(state: ReviewState) -> Approval:
    return Approval(
        analysis_id="a",
        reviewer="r",
        state=state,
    )


def test_executor_rejects_unapproved() -> None:
    ok, message, reference = MockActionExecutor().execute(
        ActionProposal(
            kind=ActionKind.CANCELLATION,
            resource_id="c",
            reason="test",
        ),
        approval=approval(ReviewState.REJECTED),
    )
    assert not ok
    assert reference is None
    assert "requires" in message


def test_executor_plan_change() -> None:
    ok, _, reference = MockActionExecutor().execute(
        ActionProposal(
            kind=ActionKind.PLAN_CHANGE,
            resource_id="c",
            target_plan="pro",
            reason="test",
        ),
        approval=approval(ReviewState.APPROVED),
    )
    assert ok and reference and reference.startswith("plan_")


def test_executor_cancel() -> None:
    ok, _, reference = MockActionExecutor().execute(
        ActionProposal(
            kind=ActionKind.CANCELLATION,
            resource_id="c",
            reason="test",
        ),
        approval=approval(ReviewState.APPROVED),
    )
    assert ok and reference and reference.startswith("cancel_")


def test_executor_rejects_ambiguous_actions() -> None:
    refund_ok, _, refund_reference = MockActionExecutor().execute(
        ActionProposal(
            kind=ActionKind.REFUND,
            resource_id="c",
            reason="test",
        ),
        approval=approval(ReviewState.APPROVED),
    )
    plan_ok, _, plan_reference = MockActionExecutor().execute(
        ActionProposal(
            kind=ActionKind.PLAN_CHANGE,
            resource_id="c",
            reason="test",
        ),
        approval=approval(ReviewState.APPROVED),
    )
    assert not refund_ok and refund_reference is None
    assert not plan_ok and plan_reference is None
