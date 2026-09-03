from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from resolveops.adapters.stripe import (
    StripeProtocolError,
    StripeProviderError,
    StripeRefundGateway,
)
from resolveops.domain.models import (
    ActionExecution,
    ActionKind,
    ActionProposal,
    ActionResourceKind,
    Approval,
    ExecutionState,
    ReviewState,
)
from resolveops.domain.outcomes import ActionOutcomeState

API_VERSION = "2026-02-25.clover"


def charge_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "ch_1",
        "object": "charge",
        "amount_captured": 10_000,
        "amount_refunded": 0,
        "captured": True,
        "currency": "usd",
        "customer": "cust_1",
        "disputed": False,
        "paid": True,
        "status": "succeeded",
        "application": None,
        "application_fee": None,
        "application_fee_amount": None,
        "on_behalf_of": None,
        "source_transfer": None,
        "transfer": None,
        "transfer_data": None,
        "transfer_group": None,
    }
    payload.update(overrides)
    return payload


def refund_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "re_1",
        "object": "refund",
        "amount": 4_000,
        "charge": "ch_1",
        "currency": "usd",
        "status": "succeeded",
    }
    payload.update(overrides)
    return payload


def action(*, amount: Decimal = Decimal("40.00"), currency: str = "usd") -> ActionProposal:
    return ActionProposal(
        kind=ActionKind.REFUND,
        resource_id="ch_1",
        resource_kind=ActionResourceKind.PAYMENT,
        resource_hash="a" * 64,
        amount=amount,
        currency=currency,
        reason="verified payment refund",
    )


def approval(*, state: ReviewState = ReviewState.APPROVED) -> Approval:
    return Approval(
        id="apr_1",
        analysis_id="ana_1",
        reviewer="manager@example.com",
        state=state,
    )


def gateway(handler, **kwargs: object) -> StripeRefundGateway:
    return StripeRefundGateway(
        secret_key="sk_test_hardening",
        api_version=API_VERSION,
        base_url="https://stripe.test/v1/",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def known_execution(*, status: str = "succeeded") -> ActionExecution:
    return ActionExecution(
        id="exe_1",
        analysis_id="ana_1",
        approval_id="apr_1",
        action=action(),
        idempotency_key="ro_hardening",
        state=ExecutionState.SUCCEEDED,
        attempt_count=1,
        external_reference="re_1",
        provider_status=status,
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"secret_key": " "}, "secret key"),
        ({"api_version": " "}, "API version"),
        ({"timeout_seconds": 0}, "timeout"),
        ({"idempotency_replay_window": timedelta(0)}, "replay window"),
        ({"idempotency_replay_window": timedelta(hours=24)}, "replay window"),
        ({"base_url": "http://stripe.test/v1/"}, "HTTPS"),
    ],
)
def test_configuration_fails_closed(kwargs: dict[str, object], message: str) -> None:
    base: dict[str, object] = {
        "secret_key": "sk_test_hardening",
        "api_version": API_VERSION,
        "transport": httpx.MockTransport(lambda request: httpx.Response(500, request=request)),
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=message):
        StripeRefundGateway(**base)  # type: ignore[arg-type]


def test_non_charge_identifier_and_missing_charge_do_not_fabricate_payment() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, json={"error": {"code": "resource_missing"}}, request=request)

    client = gateway(handler)
    try:
        assert client.get_payment("pi_1") is None
        assert client.get_payment("ch_missing") is None
    finally:
        client.close()

    assert calls == 1


def test_ugx_charge_uses_stripe_charge_api_compatibility_scaling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=charge_payload(currency="ugx", amount_captured=500),
            request=request,
        )

    client = gateway(handler)
    try:
        payment = client.get_payment("ch_1")
    finally:
        client.close()

    assert payment is not None
    assert payment.amount == Decimal("5.00")
    assert not payment.refundable


@pytest.mark.parametrize(
    ("connect_field", "value"),
    [
        ("application", "ca_1"),
        ("application_fee", "fee_1"),
        ("application_fee_amount", 100),
        ("on_behalf_of", "acct_1"),
        ("source_transfer", "tr_1"),
        ("transfer", "tr_1"),
        ("transfer_data", {"destination": "acct_1"}),
        ("transfer_group", "group_1"),
    ],
)
def test_connect_charge_topologies_are_visible_but_not_live_refundable(
    connect_field: str,
    value: object,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=charge_payload(**{connect_field: value}),
            request=request,
        )

    client = gateway(handler)
    try:
        payment = client.get_payment("ch_1")
    finally:
        client.close()

    assert payment is not None
    assert not payment.refundable


@pytest.mark.parametrize("currency", ["jpy", "eur", "gbp"])
def test_live_executor_is_intentionally_usd_only(currency: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("unsupported currency must fail before Stripe mutation")

    client = gateway(handler)
    try:
        result = client.execute(
            action(amount=Decimal("40"), currency=currency),
            approval=approval(),
            idempotency_key="ro_currency",
        )
    finally:
        client.close()

    assert result.state is ExecutionState.FAILED
    assert "USD" in result.message
    assert calls == 0


def test_unapproved_and_zero_amount_refunds_fail_before_provider_mutation() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("invalid local action must not call Stripe")

    client = gateway(handler)
    try:
        rejected = client.execute(
            action(),
            approval=approval(state=ReviewState.REJECTED),
            idempotency_key="ro_rejected",
        )
        zero = client.execute(
            action(amount=Decimal("0")),
            approval=approval(),
            idempotency_key="ro_zero",
        )
    finally:
        client.close()

    assert rejected.state is ExecutionState.FAILED
    assert zero.state is ExecutionState.FAILED
    assert calls == 0


@pytest.mark.parametrize("status_code", [401, 403])
def test_auth_and_permission_rejections_are_terminal_not_reconciliation_noise(
    status_code: int,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"code": "permission_error"}},
            request=request,
        )

    client = gateway(handler)
    try:
        result = client.execute(
            action(),
            approval=approval(),
            idempotency_key="ro_auth",
        )
    finally:
        client.close()

    assert result.state is ExecutionState.FAILED
    assert result.provider_status == "permission_error"


@pytest.mark.parametrize("status_code", [409, 424, 429, 500, 503])
def test_recoverable_or_indeterminate_provider_responses_preserve_uncertainty(
    status_code: int,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"error": {"code": "retry_same_identity"}},
            headers={"Request-Id": "req_1"},
            request=request,
        )

    client = gateway(handler)
    try:
        with pytest.raises(StripeProviderError) as caught:
            client.execute(
                action(),
                approval=approval(),
                idempotency_key="ro_recoverable",
            )
    finally:
        client.close()

    assert caught.value.status_code == status_code
    assert caught.value.code == "retry_same_identity"
    assert caught.value.request_id == "req_1"


def test_provider_error_does_not_leak_remote_error_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={
                "error": {
                    "code": "api_error",
                    "message": "sensitive remote diagnostic",
                }
            },
            request=request,
        )

    client = gateway(handler)
    try:
        with pytest.raises(StripeProviderError) as caught:
            client.execute(action(), approval=approval(), idempotency_key="ro_safe_error")
    finally:
        client.close()

    assert "sensitive remote diagnostic" not in str(caught.value)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"object": "payment_intent"}, "wrong object type"),
        ({"customer": None}, "invalid customer"),
        ({"currency": "USD"}, "invalid currency"),
        ({"amount_refunded": -1}, "invalid amount_refunded"),
        ({"captured": 1}, "invalid captured"),
    ],
)
def test_charge_contract_violations_fail_closed(
    overrides: dict[str, object],
    match: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=charge_payload(**overrides), request=request)

    client = gateway(handler)
    try:
        with pytest.raises(StripeProtocolError, match=match):
            client.get_payment("ch_1")
    finally:
        client.close()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("succeeded", ExecutionState.SUCCEEDED),
        ("pending", ExecutionState.SUBMITTED),
        ("requires_action", ExecutionState.SUBMITTED),
        ("failed", ExecutionState.FAILED),
        ("canceled", ExecutionState.FAILED),
        ("future_status", ExecutionState.UNKNOWN),
    ],
)
def test_refund_execution_status_mapping_is_explicit(
    status: str,
    expected: ExecutionState,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=refund_payload(status=status), request=request)

    client = gateway(handler)
    try:
        result = client.execute(
            action(),
            approval=approval(),
            idempotency_key="ro_status",
        )
    finally:
        client.close()

    assert result.state is expected
    assert result.provider_status == status


def test_successful_refund_with_substituted_amount_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=refund_payload(amount=3_999), request=request)

    client = gateway(handler)
    try:
        with pytest.raises(StripeProtocolError, match="amount differs"):
            client.execute(action(), approval=approval(), idempotency_key="ro_substitution")
    finally:
        client.close()


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("succeeded", ActionOutcomeState.VERIFIED),
        ("pending", ActionOutcomeState.PENDING),
        ("requires_action", ActionOutcomeState.REQUIRES_ACTION),
        ("failed", ActionOutcomeState.FAILED),
        ("canceled", ActionOutcomeState.FAILED),
        ("future_status", ActionOutcomeState.UNKNOWN),
    ],
)
def test_outcome_status_mapping_does_not_mutate_command_state(
    status: str,
    expected: ActionOutcomeState,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=refund_payload(status=status), request=request)

    client = gateway(handler)
    execution = known_execution()
    try:
        result = client.verify(execution)
    finally:
        client.close()

    assert result.state is expected
    assert execution.state is ExecutionState.SUCCEEDED


def test_unavailable_customer_reference_is_not_presented_as_verified_bank_reference() -> None:
    payload = refund_payload()
    payload["destination_details"] = {
        "card": {
            "reference": "not_ready",
            "reference_status": "pending",
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    client = gateway(handler)
    try:
        result = client.verify(known_execution())
    finally:
        client.close()

    assert result.state is ActionOutcomeState.VERIFIED
    assert result.customer_reference is None


def test_naive_reconciliation_clock_is_rejected_before_replay() -> None:
    fixed = datetime(2026, 9, 3, 2, 0, tzinfo=UTC)
    execution = ActionExecution(
        id="exe_unknown",
        analysis_id="ana_1",
        approval_id="apr_1",
        action=action(),
        idempotency_key="ro_unknown",
        state=ExecutionState.UNKNOWN,
        attempt_count=1,
        created_at=fixed - timedelta(minutes=1),
        updated_at=fixed,
    )
    client = gateway(
        lambda request: pytest.fail(f"unexpected provider call: {request.url}"),
        now=lambda: datetime(2026, 9, 3, 2, 1),
    )
    try:
        with pytest.raises(StripeProtocolError, match="timezone-aware"):
            client.reconcile(execution)
    finally:
        client.close()
