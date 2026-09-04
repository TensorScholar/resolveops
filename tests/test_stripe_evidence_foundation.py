"""Offline foundation tests for Stripe evidence helpers (no live calls)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from decimal import Decimal

from resolveops.adapters.actions import MockActionExecutor
from resolveops.adapters.billing import MemoryBillingReader
from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.memory import MemoryStore
from resolveops.adapters.sqlite import SQLiteStore
from resolveops.adapters.webhook_store import SQLiteWebhookStore
from resolveops.application.service import ResolveOpsService
from resolveops.domain.errors import IntegrityError
from resolveops.domain.models import PaymentSnapshot
from stripe_evidence.export_evidence import (
    assert_no_secrets_in_dir,
    export_evidence,
    scan_text_for_secrets,
)
from stripe_evidence.live_context import PINNED_API_VERSION, build_live_context
from stripe_evidence.logging_transport import (
    FaultOnceTransport,
    TeeTransport,
    sanitize_body,
    sanitize_headers,
    sanitize_json,
)
from stripe_evidence.seed_live import (
    make_ticket_for_charge,
    seed_customer_for_payment,
)
from stripe_evidence.webhook_runner import (
    append_webhook_record,
    build_webhook_processor,
    describe_signature,
)


def _webhook_store(tmp_path: Path) -> SQLiteWebhookStore:
    return SQLiteWebhookStore(tmp_path / "evidence.db")


def _payment() -> PaymentSnapshot:
    return PaymentSnapshot(
        id="ch_test_1",
        customer_id="cus_test_1",
        amount=Decimal("100.00"),
        amount_refunded=Decimal("0.00"),
        currency="usd",
        refundable=True,
        status="succeeded",
    )


def test_live_context_rejects_non_test_secret(tmp_path: Path) -> None:
    store = _webhook_store(tmp_path)
    with pytest.raises(ValueError, match="test-mode"):
        build_live_context(
            store=store,
            secret_key="sk_live_abc123",
            api_version=PINNED_API_VERSION,
            expected_livemode=False,
            endpoint_secret="whsec_abc123",
        )


def test_live_context_rejects_wrong_api_version_and_livemode(tmp_path: Path) -> None:
    store = _webhook_store(tmp_path)
    with pytest.raises(ValueError, match="exactly"):
        build_live_context(
            store=store,
            secret_key="sk_test_abc123",
            api_version="2020-01-01",
            expected_livemode=False,
            endpoint_secret="whsec_abc123",
        )
    with pytest.raises(ValueError, match="livemode"):
        build_live_context(
            store=store,
            secret_key="sk_test_abc123",
            api_version=PINNED_API_VERSION,
            expected_livemode=True,
            endpoint_secret="whsec_abc123",
        )


def test_live_context_rejects_wrong_store(tmp_path: Path) -> None:
    memory = MemoryStore()
    with pytest.raises(ValueError, match="SQLiteWebhookStore"):
        build_live_context(
            store=memory,  # type: ignore[arg-type]
            secret_key="sk_test_abc123",
            api_version=PINNED_API_VERSION,
            expected_livemode=False,
            endpoint_secret="whsec_abc123",
        )
    plain = SQLiteStore(tmp_path / "plain.db")
    with pytest.raises(ValueError, match="SQLiteWebhookStore"):
        build_live_context(
            store=plain,  # type: ignore[arg-type]
            secret_key="sk_test_abc123",
            api_version=PINNED_API_VERSION,
            expected_livemode=False,
            endpoint_secret="whsec_abc123",
        )


def test_live_context_rejects_bad_webhook_secrets(tmp_path: Path) -> None:
    store = _webhook_store(tmp_path)
    with pytest.raises(ValueError, match="endpoint secret"):
        build_live_context(
            store=store,
            secret_key="sk_test_abc123",
            api_version=PINNED_API_VERSION,
            expected_livemode=False,
            endpoint_secret="not-a-whsec",
        )
    with pytest.raises(ValueError, match="unique"):
        build_live_context(
            store=store,
            secret_key="sk_test_abc123",
            api_version=PINNED_API_VERSION,
            expected_livemode=False,
            endpoint_secrets=("whsec_dup", "whsec_dup"),
        )


def test_live_context_happy_path_shares_gateway(tmp_path: Path) -> None:
    store = _webhook_store(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={}, request=request)

    transport = httpx.MockTransport(handler)
    ctx = build_live_context(
        store=store,
        secret_key="sk_test_abc123",
        api_version=PINNED_API_VERSION,
        expected_livemode=False,
        endpoint_secret="whsec_abc123",
        transport=transport,
    )
    try:
        assert ctx.service.action_executor is ctx.gateway
        assert ctx.service.billing_reader is ctx.gateway
        assert ctx.outcomes.verifier is ctx.gateway
        assert ctx.store is store
    finally:
        ctx.gateway.close()


def test_sanitizer_redacts_secrets_but_preserves_ids() -> None:
    headers = httpx.Headers(
        {
            "Authorization": "Bearer sk_test_abc123",
            "Request-Id": "req_123",
            "Idempotency-Key": "ro_abc",
            "Stripe-Version": PINNED_API_VERSION,
        }
    )
    cleaned = sanitize_headers(headers)
    lowered = {key.lower(): value for key, value in cleaned.items()}
    assert lowered["authorization"] == "***REDACTED***"
    assert lowered["request-id"] == "req_123"
    assert lowered["idempotency-key"] == "ro_abc"
    assert "sk_test_" not in json.dumps(cleaned)

    payload = {
        "id": "re_1",
        "charge": "ch_1",
        "error": {"code": "charge_already_refunded", "message": "sensitive diagnostic"},
    }
    sanitized = sanitize_json(payload)
    assert sanitized["id"] == "re_1"
    assert sanitized["charge"] == "ch_1"
    assert sanitized["error"]["code"] == "charge_already_refunded"
    assert sanitized["error"]["message"] == "***REDACTED***"

    body = b"charge=ch_1&amount=4000"
    form = sanitize_body(body, "application/x-www-form-urlencoded")
    assert form["body"]["charge"] == ["ch_1"]


def test_tee_transport_never_logs_authorization() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "re_1"},
            headers={"Request-Id": "req_9"},
            request=request,
        )

    tee = TeeTransport(httpx.MockTransport(handler))
    client = httpx.Client(
        base_url="https://stripe.test/v1/",
        headers={"Authorization": "Bearer sk_test_abc123"},
        transport=tee,
    )
    try:
        response = client.post("refunds", data={"charge": "ch_1"})
    finally:
        client.close()
    assert response.status_code == 200
    assert len(tee.records) == 1
    record = tee.records[0]
    assert record["request_id"] == "req_9"
    assert "sk_test_" not in json.dumps(record)
    assert "Bearer" not in json.dumps(record)


def test_fault_once_transport_replays_same_body_and_key() -> None:
    effects: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers.get("Idempotency-Key", "")
        if key not in effects:
            effects[key] = {"id": "re_1", "object": "refund"}
        return httpx.Response(200, json=effects[key], request=request)

    fault = FaultOnceTransport(httpx.MockTransport(handler))
    client = httpx.Client(base_url="https://stripe.test/v1/", transport=fault)
    try:
        with pytest.raises(httpx.ReadTimeout):
            client.post(
                "refunds",
                data={"charge": "ch_1", "amount": "4000"},
                headers={"Idempotency-Key": "ro_same"},
            )
        second = client.post(
            "refunds",
            data={"charge": "ch_1", "amount": "4000"},
            headers={"Idempotency-Key": "ro_same"},
        )
    finally:
        client.close()
    assert second.status_code == 200
    assert len(effects) == 1
    assert len(fault.forwarded_bodies) == 1
    assert fault.forwarded_keys == ["ro_same"]


def test_export_manifest_and_secret_scan(tmp_path: Path) -> None:
    store = _webhook_store(tmp_path)
    out_dir = tmp_path / "export"
    manifest_path = export_evidence(
        store=store,
        out_dir=out_dir,
        run_id="ev-test-01",
        api_version=PINNED_API_VERSION,
        repo_rev="90407c5",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == "ev-test-01"
    assert manifest["counts"]["audit_events"] == 0
    for name, digest in manifest["files"].items():
        assert len(digest) == 64
        assert (out_dir / name).exists()

    assert scan_text_for_secrets("charge ch_1 refund re_1") == []
    assert "stripe_test_key" in scan_text_for_secrets("key sk_test_abc123")
    (out_dir / "leak.json").write_text('{"k":"sk_test_abc123"}', encoding="utf-8")
    with pytest.raises(ValueError, match="secret"):
        assert_no_secrets_in_dir(out_dir)


def test_seed_live_ownership(tmp_path: Path) -> None:
    store = _webhook_store(tmp_path)
    service = ResolveOpsService(
        store=store,
        generator=DeterministicResponseGenerator(),
        action_executor=MockActionExecutor(),
        billing_reader=MemoryBillingReader([_payment()]),
    )
    profile = seed_customer_for_payment(service, _payment())
    assert profile.id == "cus_test_1"
    again = seed_customer_for_payment(service, _payment())
    assert again.id == "cus_test_1"

    ticket = make_ticket_for_charge(
        payment=_payment(),
        ticket_customer_id="cus_test_1",
        message="Refund $10.00",
    )
    assert ticket.payment_reference == "ch_test_1"
    with pytest.raises(IntegrityError, match="does not own"):
        make_ticket_for_charge(
            payment=_payment(),
            ticket_customer_id="cus_other",
            message="Refund $10.00",
        )


def test_webhook_runner_guards_and_capture(tmp_path: Path) -> None:
    store = _webhook_store(tmp_path)
    memory = MemoryStore()

    class _Verifier:
        def verify(self, execution):
            raise AssertionError("must not be called here")

    with pytest.raises(ValueError, match="SQLiteWebhookStore"):
        build_webhook_processor(
            store=memory,  # type: ignore[arg-type]
            verifier=_Verifier(),  # type: ignore[arg-type]
            endpoint_secret="whsec_abc",
        )
    processor = build_webhook_processor(
        store=store,
        verifier=_Verifier(),  # type: ignore[arg-type]
        endpoint_secret="whsec_abc",
    )
    assert processor is not None

    meta = describe_signature("t=123,v1=aaa,v1=bbb")
    assert meta["t"] == 123
    assert meta["v1_count"] == 2

    log_path = tmp_path / "webhooks.jsonl"
    record = append_webhook_record(
        log_path=log_path,
        body=b'{"id":"evt_1"}',
        signature_header="t=123,v1=aaa",
        decision={"status": "processed", "event_id": "evt_1"},
    )
    assert record["decision"]["status"] == "processed"
    assert len(record["body_sha256"]) == 64
    assert "aaa" not in log_path.read_text(encoding="utf-8")
