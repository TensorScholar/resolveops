from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest

from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.memory import MemoryStore
from resolveops.adapters.stripe import StripeProtocolError, StripeRefundGateway
from resolveops.application.service import ResolveOpsService
from resolveops.domain.models import (
    ActionExecution,
    ActionKind,
    ActionProposal,
    ActionResourceKind,
    Approval,
    CustomerProfile,
    ExecutionState,
    KnowledgeArticle,
    ReviewState,
    Ticket,
)
from resolveops.domain.outcomes import ActionOutcomeState

API_VERSION = "2026-02-25.clover"


def charge_payload(
    *,
    charge_id: str = "ch_1",
    customer_id: str = "cust_1",
    amount_captured: int = 10_000,
    amount_refunded: int = 0,
    currency: str = "usd",
    captured: bool = True,
    paid: bool = True,
    disputed: bool = False,
    status: str = "succeeded",
) -> dict[str, object]:
    return {
        "id": charge_id,
        "object": "charge",
        "amount": amount_captured,
        "amount_captured": amount_captured,
        "amount_refunded": amount_refunded,
        "captured": captured,
        "currency": currency,
        "customer": customer_id,
        "disputed": disputed,
        "paid": paid,
        "refunded": amount_refunded >= amount_captured,
        "status": status,
    }


def refund_payload(
    *,
    refund_id: str = "re_1",
    charge_id: str = "ch_1",
    amount: int = 4_000,
    currency: str = "usd",
    status: str = "succeeded",
    reference: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": refund_id,
        "object": "refund",
        "amount": amount,
        "charge": charge_id,
        "currency": currency,
        "metadata": {},
        "status": status,
    }
    if reference is not None:
        payload["destination_details"] = {
            "card": {
                "reference": reference,
                "reference_status": "available",
                "reference_type": "acquirer_reference_number",
                "type": "refund",
            },
            "type": "card",
        }
    return payload


def refund_action(
    *,
    amount: Decimal = Decimal("40.00"),
    currency: str = "usd",
) -> ActionProposal:
    return ActionProposal(
        kind=ActionKind.REFUND,
        resource_id="ch_1",
        resource_kind=ActionResourceKind.PAYMENT,
        resource_hash="a" * 64,
        amount=amount,
        currency=currency,
        reason="verified duplicate charge",
    )


def approved() -> Approval:
    return Approval(
        id="apr_1",
        analysis_id="ana_1",
        reviewer="manager@example.com",
        state=ReviewState.APPROVED,
    )


def make_gateway(handler, **kwargs) -> StripeRefundGateway:
    return StripeRefundGateway(
        secret_key="sk_test_resolveops_unit",
        api_version=API_VERSION,
        base_url="https://stripe.test/v1/",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_charge_lookup_is_exact_and_normalizes_minor_units() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/charges/ch_1"
        assert request.headers["Authorization"] == "Bearer sk_test_resolveops_unit"
        assert request.headers["Stripe-Version"] == API_VERSION
        return httpx.Response(
            200,
            json=charge_payload(amount_captured=10_999, amount_refunded=100),
            request=request,
        )

    gateway = make_gateway(handler)
    try:
        payment = gateway.get_payment("ch_1")
    finally:
        gateway.close()

    assert payment is not None
    assert payment.id == "ch_1"
    assert payment.amount == Decimal("109.99")
    assert payment.amount_refunded == Decimal("1.00")
    assert payment.remaining_refundable == Decimal("108.99")
    assert payment.refundable


def test_zero_decimal_charge_is_not_divided_by_one_hundred() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=charge_payload(amount_captured=10_999, currency="jpy"),
            request=request,
        )

    gateway = make_gateway(handler)
    try:
        payment = gateway.get_payment("ch_1")
    finally:
        gateway.close()

    assert payment is not None
    assert payment.amount == Decimal("10999")
    assert payment.currency == "jpy"


def test_disputed_charge_is_not_refundable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=charge_payload(disputed=True), request=request)

    gateway = make_gateway(handler)
    try:
        payment = gateway.get_payment("ch_1")
    finally:
        gateway.close()

    assert payment is not None
    assert not payment.refundable


def test_charge_lookup_rejects_provider_identity_substitution() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=charge_payload(charge_id="ch_other"), request=request)

    gateway = make_gateway(handler)
    try:
        with pytest.raises(StripeProtocolError, match="mismatched identity"):
            gateway.get_payment("ch_1")
    finally:
        gateway.close()


def test_refund_submission_binds_charge_amount_metadata_and_idempotency() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/refunds"
        observed["key"] = request.headers["Idempotency-Key"]
        observed["body"] = parse_qs(request.content.decode())
        return httpx.Response(200, json=refund_payload(), request=request)

    gateway = make_gateway(handler)
    try:
        result = gateway.execute(
            refund_action(),
            approval=approved(),
            idempotency_key="ro_stable_test_key",
        )
    finally:
        gateway.close()

    assert result.state is ExecutionState.SUCCEEDED
    assert result.external_reference == "re_1"
    assert observed["key"] == "ro_stable_test_key"
    body = observed["body"]
    assert isinstance(body, dict)
    assert body["charge"] == ["ch_1"]
    assert body["amount"] == ["4000"]
    assert body["reason"] == ["requested_by_customer"]
    assert body["metadata[resolveops_analysis_id]"] == ["ana_1"]
    assert body["metadata[resolveops_approval_id]"] == ["apr_1"]
    assert len(body["metadata[resolveops_idempotency_hash]"][0]) == 64


def test_provider_current_state_rejection_is_terminal_for_that_immutable_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "type": "invalid_request_error",
                    "code": "charge_already_refunded",
                }
            },
            request=request,
        )

    gateway = make_gateway(handler)
    try:
        result = gateway.execute(
            refund_action(),
            approval=approved(),
            idempotency_key="ro_already_refunded",
        )
    finally:
        gateway.close()

    assert result.state is ExecutionState.FAILED
    assert result.external_reference is None
    assert result.provider_status == "charge_already_refunded"


def test_lost_response_reconciliation_replays_exact_same_request_and_key_once() -> None:
    provider_effects: dict[str, dict[str, object]] = {}
    first_bodies: dict[str, bytes] = {}
    post_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls
        if request.method == "GET" and request.url.path == "/v1/charges/ch_1":
            return httpx.Response(200, json=charge_payload(), request=request)
        if request.method == "POST" and request.url.path == "/v1/refunds":
            post_calls += 1
            key = request.headers["Idempotency-Key"]
            if key not in provider_effects:
                first_bodies[key] = request.content
                provider_effects[key] = refund_payload()
                raise httpx.ReadTimeout("response lost after provider side effect", request=request)
            assert request.content == first_bodies[key]
            return httpx.Response(200, json=provider_effects[key], request=request)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    gateway = make_gateway(handler)
    store = MemoryStore()
    service = ResolveOpsService(
        store=store,
        generator=DeterministicResponseGenerator(),
        action_executor=gateway,
        billing_reader=gateway,
    )
    service.seed_customer(CustomerProfile(id="cust_1"))
    service.seed_article(
        KnowledgeArticle(
            id="kb_refund",
            title="Refund policy",
            body="Refunds up to $250 require human approval.",
            source_uri="kb://refund",
            owner="support",
        )
    )
    try:
        analysis = service.analyze(
            Ticket(customer_id="cust_1", message="Refund $40", payment_reference="ch_1")
        )
        _, uncertain = service.review(
            analysis.id,
            reviewer="manager@example.com",
            approve=True,
        )
        assert uncertain is not None
        assert uncertain.state is ExecutionState.UNKNOWN
        assert uncertain.attempt_count == 1
        assert uncertain.external_reference is None
        assert len(provider_effects) == 1

        recovered = service.reconcile_execution(uncertain.id)
    finally:
        gateway.close()

    assert recovered.state is ExecutionState.SUCCEEDED
    assert recovered.external_reference == "re_1"
    assert recovered.attempt_count == 2
    assert post_calls == 2
    assert len(provider_effects) == 1
    service.verify_audit()


def test_unknown_operation_is_not_blindly_replayed_after_safe_window() -> None:
    fixed_now = datetime(2026, 9, 3, 2, 0, tzinfo=UTC)
    called = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called += 1
        raise AssertionError("expired idempotency recovery must not call Stripe")

    gateway = make_gateway(handler, now=lambda: fixed_now)
    execution = ActionExecution(
        id="exe_old",
        analysis_id="ana_1",
        approval_id="apr_1",
        action=refund_action(),
        idempotency_key="ro_old",
        state=ExecutionState.UNKNOWN,
        attempt_count=1,
        created_at=fixed_now - timedelta(hours=23, seconds=1),
        updated_at=fixed_now - timedelta(hours=23),
    )
    try:
        result = gateway.reconcile(execution)
    finally:
        gateway.close()

    assert result.state is ExecutionState.UNKNOWN
    assert result.external_reference is None
    assert "manual" in result.message.casefold()
    assert called == 0


def test_known_refund_reconciliation_uses_exact_get_not_post() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        return httpx.Response(200, json=refund_payload(status="succeeded"), request=request)

    gateway = make_gateway(handler)
    execution = ActionExecution(
        id="exe_known",
        analysis_id="ana_1",
        approval_id="apr_1",
        action=refund_action(),
        idempotency_key="ro_known",
        state=ExecutionState.SUBMITTED,
        attempt_count=1,
        external_reference="re_1",
        provider_status="pending",
    )
    try:
        result = gateway.reconcile(execution)
    finally:
        gateway.close()

    assert result.state is ExecutionState.SUCCEEDED
    assert calls == ["GET /v1/refunds/re_1"]


def test_outcome_verification_can_change_after_execution_succeeded() -> None:
    statuses = iter(
        [
            refund_payload(status="succeeded", reference="arn_123"),
            refund_payload(status="failed"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/refunds/re_1"
        return httpx.Response(200, json=next(statuses), request=request)

    gateway = make_gateway(handler)
    execution = ActionExecution(
        id="exe_verified_then_failed",
        analysis_id="ana_1",
        approval_id="apr_1",
        action=refund_action(),
        idempotency_key="ro_verified_then_failed",
        state=ExecutionState.SUCCEEDED,
        attempt_count=1,
        external_reference="re_1",
        provider_status="succeeded",
    )
    try:
        first = gateway.verify(execution)
        second = gateway.verify(execution)
    finally:
        gateway.close()

    assert first.state is ActionOutcomeState.VERIFIED
    assert first.customer_reference == "arn_123"
    assert second.state is ActionOutcomeState.FAILED
    assert execution.state is ExecutionState.SUCCEEDED
