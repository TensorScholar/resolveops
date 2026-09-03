from __future__ import annotations

import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from resolveops.adapters.actions import MockActionExecutor
from resolveops.adapters.billing import MemoryBillingReader
from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.webhook_store import SQLiteWebhookStore
from resolveops.application.service import ResolveOpsService
from resolveops.application.stripe_webhooks import (
    StripeWebhookProcessor,
    StripeWebhookProtocolError,
    StripeWebhookSignatureError,
)
from resolveops.domain.errors import IntegrityError, NotFoundError
from resolveops.domain.models import CustomerProfile, KnowledgeArticle, PaymentSnapshot, Ticket
from resolveops.domain.outcomes import ActionOutcomeResult, ActionOutcomeState

_SECRET = "whsec_test_only"
_NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


@dataclass
class StaticVerifier:
    result: ActionOutcomeResult | None = None
    error: Exception | None = None
    calls: int = 0

    def verify(self, execution):
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _successful_execution(service: ResolveOpsService):
    analysis = service.analyze(
        Ticket(
            customer_id="cust_1",
            message="Refund $49",
            payment_reference="pay_cust_1",
        )
    )
    _, execution = service.review(
        analysis.id,
        reviewer="manager@example.com",
        approve=True,
    )
    assert execution is not None
    assert execution.external_reference is not None
    return execution


def _event(refund_id: str, *, event_id: str = "evt_1", event_type: str = "refund.updated") -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "type": event_type,
            "livemode": False,
            "data": {
                "object": {
                    "id": refund_id,
                    "object": "refund",
                    "status": "failed",
                }
            },
        },
        separators=(",", ":"),
    ).encode()


def _signature(body: bytes, *, timestamp: int | None = None, secret: str = _SECRET) -> str:
    signed_at = int(_NOW.timestamp()) if timestamp is None else timestamp
    digest = hmac.new(
        secret.encode(),
        str(signed_at).encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return f"t={signed_at},v1={digest}"


def _processor(store, verifier: StaticVerifier) -> StripeWebhookProcessor:
    return StripeWebhookProcessor(
        store=store,
        verifier=verifier,
        endpoint_secret=_SECRET,
        expected_livemode=False,
        now=lambda: _NOW,
    )


def test_signed_webhook_triggers_current_provider_read_not_payload_status(service) -> None:
    execution = _successful_execution(service)
    verifier = StaticVerifier(
        result=ActionOutcomeResult(
            state=ActionOutcomeState.VERIFIED,
            provider_reference=execution.external_reference,
            provider_status="succeeded",
            message="Current provider read reports success.",
        )
    )
    body = _event(execution.external_reference)

    result = _processor(service.store, verifier).process(body, _signature(body))

    assert result["status"] == "processed"
    assert result["outcome"] == "verified"
    assert verifier.calls == 1
    outcome_events = [
        event for event in service.store.list_audit() if event.event_type == "action.outcome_observed"
    ]
    assert len(outcome_events) == 1
    assert outcome_events[0].payload["stripe_event_id"] == "evt_1"
    assert outcome_events[0].payload["stripe_event_type"] == "refund.updated"
    service.verify_audit()


def test_duplicate_event_is_committed_once(service) -> None:
    execution = _successful_execution(service)
    verifier = StaticVerifier(
        result=ActionOutcomeResult(
            state=ActionOutcomeState.VERIFIED,
            provider_reference=execution.external_reference,
            provider_status="succeeded",
            message="verified",
        )
    )
    processor = _processor(service.store, verifier)
    body = _event(execution.external_reference)
    signature = _signature(body)

    first = processor.process(body, signature)
    second = processor.process(body, signature)

    assert first["status"] == "processed"
    assert second == {"status": "duplicate", "event_id": "evt_1"}
    assert verifier.calls == 2
    assert len(
        [event for event in service.store.list_audit() if event.event_type == "action.outcome_observed"]
    ) == 1


def test_invalid_signature_and_timestamp_replay_are_rejected(service) -> None:
    execution = _successful_execution(service)
    verifier = StaticVerifier()
    processor = _processor(service.store, verifier)
    body = _event(execution.external_reference)

    with pytest.raises(StripeWebhookSignatureError, match="mismatch"):
        processor.process(body, _signature(body, secret="wrong"))
    with pytest.raises(StripeWebhookSignatureError, match="outside tolerance"):
        processor.process(
            body,
            _signature(body, timestamp=int((_NOW - timedelta(minutes=6)).timestamp())),
        )
    assert verifier.calls == 0


def test_livemode_crossing_and_unknown_refund_fail_closed(service) -> None:
    execution = _successful_execution(service)
    verifier = StaticVerifier()
    processor = _processor(service.store, verifier)
    raw = json.loads(_event(execution.external_reference))
    raw["livemode"] = True
    live_body = json.dumps(raw, separators=(",", ":")).encode()

    with pytest.raises(StripeWebhookProtocolError, match="livemode"):
        processor.process(live_body, _signature(live_body))

    missing = _event("re_missing", event_id="evt_missing")
    with pytest.raises(NotFoundError, match="not yet available"):
        processor.process(missing, _signature(missing))
    assert verifier.calls == 0


def test_unsupported_signed_event_is_acknowledged_without_provider_read(service) -> None:
    execution = _successful_execution(service)
    verifier = StaticVerifier()
    body = _event(
        execution.external_reference,
        event_id="evt_unrelated",
        event_type="charge.updated",
    )

    result = _processor(service.store, verifier).process(body, _signature(body))

    assert result == {"status": "ignored", "event_id": "evt_unrelated"}
    assert verifier.calls == 0


def test_provider_read_failure_is_audited_as_unknown_and_deduplicated(service) -> None:
    execution = _successful_execution(service)
    verifier = StaticVerifier(error=TimeoutError("provider unavailable"))
    processor = _processor(service.store, verifier)
    body = _event(execution.external_reference)

    first = processor.process(body, _signature(body))
    second = processor.process(body, _signature(body))

    assert first["outcome"] == "unknown"
    assert second["status"] == "duplicate"
    assert len(
        [event for event in service.store.list_audit() if event.event_type == "action.outcome_observed"]
    ) == 1


def test_provider_cannot_substitute_refund_identity(service) -> None:
    execution = _successful_execution(service)
    verifier = StaticVerifier(
        result=ActionOutcomeResult(
            state=ActionOutcomeState.VERIFIED,
            provider_reference="re_different",
            provider_status="succeeded",
            message="wrong refund",
        )
    )
    body = _event(execution.external_reference)

    with pytest.raises(IntegrityError, match="different provider operation"):
        _processor(service.store, verifier).process(body, _signature(body))
    assert not any(
        event.payload.get("stripe_event_id") == "evt_1" for event in service.store.list_audit()
    )


def _sqlite_service(path) -> ResolveOpsService:
    store = SQLiteWebhookStore(path)
    service = ResolveOpsService(
        store=store,
        generator=DeterministicResponseGenerator(),
        action_executor=MockActionExecutor(),
        billing_reader=MemoryBillingReader(
            (
                PaymentSnapshot(
                    id="pay_cust_1",
                    customer_id="cust_1",
                    amount=Decimal("100.00"),
                    amount_refunded=Decimal("0.00"),
                    currency="usd",
                    refundable=True,
                    status="succeeded",
                ),
            )
        ),
    )
    service.seed_customer(CustomerProfile(id="cust_1"))
    service.seed_article(
        KnowledgeArticle(
            id="kb_refund",
            title="Refund policy",
            body="Refunds require human approval.",
            source_uri="kb://refund",
            owner="support",
            updated_at=_NOW,
        )
    )
    return service


def test_concurrent_sqlite_delivery_commits_one_outcome(tmp_path) -> None:
    path = tmp_path / "webhooks.db"
    setup_service = _sqlite_service(path)
    execution = _successful_execution(setup_service)
    verifier = StaticVerifier(
        result=ActionOutcomeResult(
            state=ActionOutcomeState.VERIFIED,
            provider_reference=execution.external_reference,
            provider_status="succeeded",
            message="verified",
        )
    )
    body = _event(execution.external_reference)
    signature = _signature(body)

    def deliver() -> str:
        store = SQLiteWebhookStore(path)
        result = _processor(store, verifier).process(body, signature)
        return result["status"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: deliver(), range(2)))

    assert statuses == ["duplicate", "processed"]
    restarted = SQLiteWebhookStore(path)
    matching = [
        event
        for event in restarted.list_audit()
        if event.event_type == "action.outcome_observed"
        and event.payload.get("stripe_event_id") == "evt_1"
    ]
    assert len(matching) == 1
