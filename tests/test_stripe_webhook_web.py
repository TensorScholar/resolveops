from __future__ import annotations

from dataclasses import dataclass

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from resolveops.application.stripe_webhooks import (
    StripeWebhookProtocolError,
    StripeWebhookSignatureError,
)
from resolveops.domain.errors import IntegrityError, NotFoundError
from resolveops.web.stripe import create_stripe_webhook_app


@dataclass
class StubProcessor:
    result: dict[str, str] | None = None
    error: Exception | None = None
    body: bytes | None = None
    signature: str | None = None

    def process(self, body: bytes, signature_header: str) -> dict[str, str]:
        self.body = body
        self.signature = signature_header
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def test_webhook_ingress_forwards_raw_body_and_signature() -> None:
    processor = StubProcessor(result={"status": "processed", "event_id": "evt_1"})
    client = TestClient(create_stripe_webhook_app(processor))
    body = b'{"id":"evt_1"}'

    response = client.post(
        "/webhooks/stripe",
        content=body,
        headers={"stripe-signature": "t=1,v1=abc"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert processor.body == body
    assert processor.signature == "t=1,v1=abc"


def test_webhook_ingress_requires_signature_and_limits_body() -> None:
    processor = StubProcessor(result={"status": "ignored", "event_id": "evt"})
    client = TestClient(create_stripe_webhook_app(processor))

    assert client.post("/webhooks/stripe", content=b"{}").status_code == 400
    oversized = b"x" * (256 * 1024 + 1)
    response = client.post(
        "/webhooks/stripe",
        content=oversized,
        headers={"stripe-signature": "t=1,v1=abc"},
    )
    assert response.status_code == 413
    assert processor.body is None


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (StripeWebhookSignatureError("bad"), 400),
        (StripeWebhookProtocolError("bad"), 400),
        (NotFoundError("race"), 503),
        (IntegrityError("conflict"), 409),
    ],
)
def test_webhook_ingress_maps_failures_without_leaking_details(
    error: Exception,
    status_code: int,
) -> None:
    processor = StubProcessor(error=error)
    client = TestClient(create_stripe_webhook_app(processor))

    response = client.post(
        "/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "t=1,v1=abc"},
    )

    assert response.status_code == status_code
    assert str(error) not in response.text
