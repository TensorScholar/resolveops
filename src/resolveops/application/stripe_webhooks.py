"""Authenticated Stripe refund webhook ingestion as a trigger for current-state verification."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

from resolveops.application.outcomes import ActionOutcomeService
from resolveops.domain.audit import object_digest
from resolveops.domain.errors import IntegrityError, NotFoundError
from resolveops.domain.models import ActionExecution
from resolveops.ports.interfaces import ActionOutcomeVerifier, IdempotentAuditStore


class StripeWebhookSignatureError(ValueError):
    """The Stripe webhook signature or timestamp is invalid."""


class StripeWebhookProtocolError(ValueError):
    """The signed Stripe event violates the narrow webhook contract."""


class StripeWebhookProcessor:
    """Verify signed refund events, deduplicate them, then read current provider truth."""

    _SUPPORTED_EVENT_TYPES = frozenset({"refund.created", "refund.updated", "refund.failed"})

    def __init__(
        self,
        *,
        store: IdempotentAuditStore,
        verifier: ActionOutcomeVerifier,
        endpoint_secrets: tuple[str, ...],
        expected_livemode: bool,
        tolerance: timedelta = timedelta(minutes=5),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not endpoint_secrets:
            raise ValueError("at least one Stripe webhook endpoint secret is required")
        if any(not secret.strip() for secret in endpoint_secrets):
            raise ValueError("Stripe webhook endpoint secrets must not be empty")
        if len(set(endpoint_secrets)) != len(endpoint_secrets):
            raise ValueError("Stripe webhook endpoint secrets must be unique")
        if tolerance <= timedelta(0):
            raise ValueError("Stripe webhook signature tolerance must be positive")
        self._store = store
        self._outcomes = ActionOutcomeService(store=store, verifier=verifier)
        self._secrets = tuple(secret.encode() for secret in endpoint_secrets)
        self._expected_livemode = expected_livemode
        self._tolerance = tolerance
        self._now = now or (lambda: datetime.now(UTC))

    def _verify_signature(self, body: bytes, signature_header: str) -> int:
        timestamp: int | None = None
        signatures: list[str] = []
        for item in signature_header.split(","):
            key, separator, value = item.strip().partition("=")
            if not separator or not value:
                continue
            if key == "t":
                try:
                    timestamp = int(value)
                except ValueError as exc:
                    raise StripeWebhookSignatureError(
                        "Stripe webhook timestamp is invalid"
                    ) from exc
            elif key == "v1":
                signatures.append(value)

        if timestamp is None or not signatures:
            raise StripeWebhookSignatureError("Stripe webhook signature is incomplete")
        current = self._now()
        if current.tzinfo is None:
            raise StripeWebhookProtocolError("Stripe webhook clock must be timezone-aware")
        signed_at = datetime.fromtimestamp(timestamp, tz=UTC)
        if abs(current - signed_at) > self._tolerance:
            raise StripeWebhookSignatureError("Stripe webhook timestamp is outside tolerance")

        signed_payload = str(timestamp).encode() + b"." + body
        matched = False
        for secret in self._secrets:
            expected = hmac.new(secret, signed_payload, hashlib.sha256).hexdigest()
            for candidate in signatures:
                candidate_matches = hmac.compare_digest(expected, candidate)
                matched = candidate_matches or matched
        if not matched:
            raise StripeWebhookSignatureError("Stripe webhook signature mismatch")
        return timestamp

    @staticmethod
    def _json_object(body: bytes) -> dict[str, object]:
        try:
            raw: object = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StripeWebhookProtocolError("Stripe webhook body is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise StripeWebhookProtocolError("Stripe webhook event is not an object")
        return cast(dict[str, object], raw)

    @staticmethod
    def _required_str(payload: dict[str, object], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise StripeWebhookProtocolError(f"Stripe webhook event has invalid {key}")
        return value

    def _execution_for_refund(self, refund_id: str) -> ActionExecution:
        matches = [
            execution
            for execution in self._store.list_executions()
            if execution.external_reference == refund_id
        ]
        if not matches:
            raise NotFoundError(f"execution not yet available for Stripe refund: {refund_id}")
        if len(matches) != 1:
            raise IntegrityError("multiple executions reference the same Stripe refund")
        return matches[0]

    def process(self, body: bytes, signature_header: str) -> dict[str, str]:
        """Process one signed Stripe event without trusting its embedded refund status."""
        signature_timestamp = self._verify_signature(body, signature_header)
        event = self._json_object(body)
        event_id = self._required_str(event, "id")
        event_type = self._required_str(event, "type")
        livemode = event.get("livemode")
        if not isinstance(livemode, bool):
            raise StripeWebhookProtocolError("Stripe webhook event has invalid livemode")
        if livemode is not self._expected_livemode:
            raise StripeWebhookProtocolError("Stripe webhook livemode does not match deployment")
        if event_type not in self._SUPPORTED_EVENT_TYPES:
            return {"status": "ignored", "event_id": event_id}

        data = event.get("data")
        if not isinstance(data, dict):
            raise StripeWebhookProtocolError("Stripe webhook event has invalid data")
        raw_object = data.get("object")
        if not isinstance(raw_object, dict) or raw_object.get("object") != "refund":
            raise StripeWebhookProtocolError("Stripe refund webhook has invalid data object")
        refund_id = self._required_str(cast(dict[str, object], raw_object), "id")
        execution = self._execution_for_refund(refund_id)

        unique_event_key = f"stripe:{int(self._expected_livemode)}:{event_id}"
        event_identity_hash = object_digest(
            {
                "provider": "stripe",
                "livemode": livemode,
                "event_id": event_id,
                "event_type": event_type,
                "refund_id": refund_id,
            }
        )
        observation = self._outcomes.observe_external(
            execution.id,
            stripe_event_id=event_id,
            stripe_event_type=event_type,
            stripe_signature_timestamp=signature_timestamp,
            external_event_identity_hash=event_identity_hash,
            unique_event_key=unique_event_key,
        )
        if observation is None:
            return {"status": "duplicate", "event_id": event_id}
        return {
            "status": "processed",
            "event_id": event_id,
            "execution_id": execution.id,
            "outcome": observation.state.value,
        }
