"""Safe composition for Stripe test-mode evidence runs.

Builds the live ResolveOps transaction from one gateway instance so the
billing reader, action executor, and outcome verifier cannot diverge.
Fails closed unless every test-mode guard holds. No live calls here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx

from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.stripe import StripeRefundGateway
from resolveops.adapters.webhook_store import SQLiteWebhookStore
from resolveops.application.outcomes import ActionOutcomeService
from resolveops.application.service import ResolveOpsService
from resolveops.application.stripe_webhooks import StripeWebhookProcessor

PINNED_API_VERSION = "2026-02-25.clover"


@dataclass(frozen=True)
class LiveContext:
    """One consistent live wiring: single gateway shared by all ports."""

    store: SQLiteWebhookStore
    gateway: StripeRefundGateway
    service: ResolveOpsService
    outcomes: ActionOutcomeService
    processor: StripeWebhookProcessor


def _require_test_secret(secret_key: str) -> None:
    if not isinstance(secret_key, str) or not secret_key.strip():
        raise ValueError("Stripe secret key must not be empty")
    if not secret_key.startswith("sk_test_"):
        raise ValueError("Stripe secret key must be a test-mode key (sk_test_ only)")


def _require_pinned_version(api_version: str) -> None:
    if api_version != PINNED_API_VERSION:
        raise ValueError(f"Stripe API version must be exactly {PINNED_API_VERSION}")


def _require_webhook_secrets(
    endpoint_secret: str | None,
    endpoint_secrets: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if (endpoint_secret is None) == (endpoint_secrets is None):
        raise ValueError("configure exactly one webhook secret or secret set")
    configured = (endpoint_secret,) if endpoint_secret is not None else endpoint_secrets
    assert configured is not None
    if not configured:
        raise ValueError("at least one webhook endpoint secret is required")
    for secret in configured:
        if not isinstance(secret, str) or not secret.strip():
            raise ValueError("webhook endpoint secrets must not be empty")
        if not secret.startswith("whsec_"):
            raise ValueError("webhook endpoint secrets must be test endpoint secrets")
    if len(set(configured)) != len(configured):
        raise ValueError("webhook endpoint secrets must be unique")
    return tuple(configured)


def build_live_context(
    *,
    store: SQLiteWebhookStore,
    secret_key: str,
    api_version: str,
    expected_livemode: bool,
    endpoint_secret: str | None = None,
    endpoint_secrets: tuple[str, ...] | None = None,
    transport: httpx.BaseTransport | None = None,
    timeout_seconds: float = 10.0,
    tolerance: timedelta = timedelta(minutes=5),
    now: Callable[[], datetime] | None = None,
) -> LiveContext:
    """Build a consistent live context or raise without side effects."""
    if not isinstance(store, SQLiteWebhookStore):
        raise ValueError("store must be SQLiteWebhookStore for webhook evidence")
    _require_test_secret(secret_key)
    _require_pinned_version(api_version)
    if expected_livemode is not False:
        raise ValueError("expected_livemode must be False for test-mode evidence")
    secrets = _require_webhook_secrets(endpoint_secret, endpoint_secrets)

    gateway = StripeRefundGateway(
        secret_key=secret_key,
        api_version=api_version,
        transport=transport,
        timeout_seconds=timeout_seconds,
    )
    service = ResolveOpsService(
        store=store,
        generator=DeterministicResponseGenerator(),
        action_executor=gateway,
        billing_reader=gateway,
    )
    outcomes = ActionOutcomeService(store=store, verifier=gateway)
    if len(secrets) == 1:
        processor = StripeWebhookProcessor(
            store=store,
            verifier=gateway,
            expected_livemode=False,
            endpoint_secret=secrets[0],
            tolerance=tolerance,
            now=now,
        )
    else:
        processor = StripeWebhookProcessor(
            store=store,
            verifier=gateway,
            expected_livemode=False,
            endpoint_secrets=secrets,
            tolerance=tolerance,
            now=now,
        )

    if service.action_executor is not gateway or service.billing_reader is not gateway:
        gateway.close()
        raise ValueError("live service must share one gateway instance")
    if outcomes.verifier is not gateway:
        gateway.close()
        raise ValueError("live outcome verifier must share one gateway instance")
    return LiveContext(
        store=store,
        gateway=gateway,
        service=service,
        outcomes=outcomes,
        processor=processor,
    )
