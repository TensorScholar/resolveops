"""Loopback webhook construction and sanitized delivery capture."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from resolveops.adapters.webhook_store import SQLiteWebhookStore
from resolveops.application.stripe_webhooks import StripeWebhookProcessor
from resolveops.ports.interfaces import ActionOutcomeVerifier


def build_webhook_processor(
    *,
    store: SQLiteWebhookStore,
    verifier: ActionOutcomeVerifier,
    expected_livemode: bool = False,
    endpoint_secret: str | None = None,
    endpoint_secrets: tuple[str, ...] | None = None,
    tolerance: timedelta = timedelta(minutes=5),
    now: Callable[[], datetime] | None = None,
) -> StripeWebhookProcessor:
    """Construct the webhook processor with test-mode guards."""
    if not isinstance(store, SQLiteWebhookStore):
        raise ValueError("webhook store must be SQLiteWebhookStore")
    if expected_livemode is not False:
        raise ValueError("expected_livemode must be False for test-mode evidence")
    if (endpoint_secret is None) == (endpoint_secrets is None):
        raise ValueError("configure exactly one webhook secret or secret set")
    configured = (endpoint_secret,) if endpoint_secret is not None else endpoint_secrets
    assert configured is not None
    for secret in configured:
        if not isinstance(secret, str) or not secret.strip():
            raise ValueError("webhook endpoint secrets must not be empty")
        if not secret.startswith("whsec_"):
            raise ValueError("webhook endpoint secrets must be test endpoint secrets")
    if len(secrets := tuple(configured)) != len(set(secrets)):
        raise ValueError("webhook endpoint secrets must be unique")
    if len(secrets) == 1:
        return StripeWebhookProcessor(
            store=store,
            verifier=verifier,
            expected_livemode=False,
            endpoint_secret=secrets[0],
            tolerance=tolerance,
            now=now,
        )
    return StripeWebhookProcessor(
        store=store,
        verifier=verifier,
        expected_livemode=False,
        endpoint_secrets=secrets,
        tolerance=tolerance,
        now=now,
    )


def describe_signature(signature_header: str) -> dict[str, Any]:
    """Summarize a Stripe-Signature header without persisting signatures."""
    timestamp: int | None = None
    v1_count = 0
    for item in signature_header.split(","):
        key, separator, value = item.strip().partition("=")
        if not separator or not value:
            continue
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                timestamp = None
        elif key == "v1":
            v1_count += 1
    return {
        "t": timestamp,
        "v1_count": v1_count,
        "header_len": len(signature_header.encode()),
    }


def build_evidence_record(
    *,
    body: bytes,
    signature_header: str,
    decision: dict[str, str],
) -> dict[str, Any]:
    """Build a sanitized webhook delivery record (no raw signatures/secrets)."""
    meta = describe_signature(signature_header)
    return {
        "observed_at": datetime.now(UTC).isoformat(),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "body_len": len(body),
        "signature_t": meta["t"],
        "signature_v1_count": meta["v1_count"],
        "decision": dict(decision),
    }


def append_webhook_record(
    *,
    log_path: str | Path,
    body: bytes,
    signature_header: str,
    decision: dict[str, str],
) -> dict[str, Any]:
    """Append one sanitized delivery record as JSONL; return the record."""
    record = build_evidence_record(body=body, signature_header=signature_header, decision=decision)
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def build_capturing_app(
    *,
    processor: StripeWebhookProcessor,
    log_path: str | Path,
) -> Any:
    """Create the loopback webhook app with sanitized per-delivery capture."""
    try:
        from fastapi import FastAPI, HTTPException, Request
    except ImportError as exc:
        raise RuntimeError("Install ResolveOps with the 'web' extra.") from exc
    from resolveops.application.outcomes import OutcomeVerificationUnavailableError
    from resolveops.application.stripe_webhooks import (
        StripeWebhookProtocolError,
        StripeWebhookSignatureError,
    )
    from resolveops.domain.errors import IntegrityError, NotFoundError

    app = FastAPI(title="ResolveOps Stripe Webhook (evidence capture)")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/stripe")
    async def stripe_webhook(request: Request) -> dict[str, str]:
        signature = request.headers.get("stripe-signature", "")
        body = await request.body()
        try:
            decision = processor.process(body, signature)
        except (StripeWebhookSignatureError, StripeWebhookProtocolError) as exc:
            append_webhook_record(
                log_path=log_path,
                body=body,
                signature_header=signature,
                decision={"status": "rejected"},
            )
            raise HTTPException(status_code=400, detail="Invalid Stripe webhook.") from exc
        except (NotFoundError, OutcomeVerificationUnavailableError) as exc:
            append_webhook_record(
                log_path=log_path,
                body=body,
                signature_header=signature,
                decision={"status": "retryable"},
            )
            raise HTTPException(
                status_code=503,
                detail="Stripe webhook processing is temporarily unavailable.",
            ) from exc
        except IntegrityError as exc:
            append_webhook_record(
                log_path=log_path,
                body=body,
                signature_header=signature,
                decision={"status": "conflict"},
            )
            raise HTTPException(
                status_code=409,
                detail="Stripe webhook conflicts with persisted execution state.",
            ) from exc
        append_webhook_record(
            log_path=log_path, body=body, signature_header=signature, decision=decision
        )
        return decision

    return app
