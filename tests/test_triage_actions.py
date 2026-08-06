from resolveops.domain.models import ActionKind, IntentKind, Ticket
from resolveops.domain.triage import propose_action


def test_plan_action() -> None:
    action = propose_action(
        Ticket(customer_id="c", message="upgrade my plan"),
        IntentKind.PLAN_CHANGE,
    )
    assert action is not None
    assert action.kind is ActionKind.PLAN_CHANGE
    assert action.target_plan == "pro"


def test_downgrade_action() -> None:
    action = propose_action(
        Ticket(customer_id="c", message="downgrade my plan"),
        IntentKind.PLAN_CHANGE,
    )
    assert action is not None
    assert action.target_plan == "basic"


def test_ambiguous_plan_action_has_no_target() -> None:
    action = propose_action(
        Ticket(customer_id="c", message="change my plan"),
        IntentKind.PLAN_CHANGE,
    )
    assert action is not None
    assert action.target_plan is None


def test_cancel_action() -> None:
    action = propose_action(
        Ticket(customer_id="c", message="cancel"),
        IntentKind.CANCELLATION,
    )
    assert action is not None and action.kind is ActionKind.CANCELLATION


def test_no_action_for_information() -> None:
    assert (
        propose_action(
            Ticket(customer_id="c", message="what"),
            IntentKind.INFORMATION,
        )
        is None
    )
