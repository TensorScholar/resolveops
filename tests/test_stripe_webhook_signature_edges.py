from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest

from resolveops.adapters.memory import MemoryStore
from resolveops.application.stripe_webhooks import (
    StripeWebhookProcessor,
    StripeWebhookProtocolError,
    StripeWebhookSignatureError,
)

_SECRET = "webhook-edge-test-secret"
_NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
_BODY = json.dumps(
    {
        "id": "evt_rotation",
        "object": "event",
        "type": "charge.updated",
        "livemode": False,
    },
    separators=(",", ":"),
).encode()


class NeverCalledVerifier:
    def verify(self, execution):
        raise AssertionError("unsupported events must not read provider state")


def _processor(*, now=lambda: _NOW, tolerance=timedelta(minutes=5)) -> StripeWebhookProcessor:
    return StripeWebhookProcessor(
        store=MemoryStore(),
        verifier=NeverCalledVerifier(),
        endpoint_secret=_SECRET,
        expected_livemode=False,
        tolerance=tolerance,
        now=now,
    )


def _digest(timestamp: int) -> str:
    return hmac.new(
        _SECRET.encode(),
        str(timestamp).encode() + b"." + _BODY,
        hashlib.sha256,
    ).hexdigest()


def test_multiple_v1_signatures_accept_when_any_signature_matches() -> None:
    timestamp = int(_NOW.timestamp())
    header = f"t={timestamp},v1={'0' * 64},v1={_digest(timestamp)}"

    result = _processor().process(_BODY, header)

    assert result == {"status": "ignored", "event_id": "evt_rotation"}


@pytest.mark.parametrize("minutes", [-6, 6])
def test_signature_timestamp_outside_tolerance_is_rejected_in_both_directions(
    minutes: int,
) -> None:
    timestamp = int((_NOW + timedelta(minutes=minutes)).timestamp())
    header = f"t={timestamp},v1={_digest(timestamp)}"

    with pytest.raises(StripeWebhookSignatureError, match="outside tolerance"):
        _processor().process(_BODY, header)


def test_malformed_or_incomplete_signature_headers_fail_closed() -> None:
    with pytest.raises(StripeWebhookSignatureError, match="timestamp is invalid"):
        _processor().process(_BODY, "t=not-an-int,v1=abc")
    with pytest.raises(StripeWebhookSignatureError, match="incomplete"):
        _processor().process(_BODY, "t=123")
    with pytest.raises(StripeWebhookSignatureError, match="incomplete"):
        _processor().process(_BODY, "v1=abc")


def test_webhook_processor_configuration_fails_closed() -> None:
    with pytest.raises(ValueError, match="secret must not be empty"):
        StripeWebhookProcessor(
            store=MemoryStore(),
            verifier=NeverCalledVerifier(),
            endpoint_secret="   ",
            expected_livemode=False,
        )
    with pytest.raises(ValueError, match="tolerance must be positive"):
        _processor(tolerance=timedelta(0))
    with pytest.raises(StripeWebhookProtocolError, match="clock must be timezone-aware"):
        _processor(now=lambda: datetime(2026, 9, 3, 12, 0)).process(
            _BODY,
            f"t={int(_NOW.timestamp())},v1={_digest(int(_NOW.timestamp()))}",
        )
