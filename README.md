# ResolveOps

[![CI](https://github.com/TensorScholar/resolveops/actions/workflows/ci.yml/badge.svg)](https://github.com/TensorScholar/resolveops/actions/workflows/ci.yml)

**A support-resolution transaction layer for high-impact customer operations.**

ResolveOps is not another customer-service chatbot or generic agent framework. It sits between
a support system and external systems of record when a resolution can change customer or
billing state. Its job is to make that resolution inspectable from evidence through execution:

```text
support case + customer context + approved evidence
                    ↓
          deterministic business policy
                    ↓
 explicit verified-resource action proposal
                    ↓
             human review if required
                    ↓
     durable execution claim + idempotency key
                    ↓
      durable in-flight provider interaction
                    ↓
        provider result / reconciliation
                    ↓
 authenticated outcome trigger + provider-current verification
                    ↓
          verified support outcome + audit
```

The product boundary is intentionally narrow: ResolveOps owns the **support-resolution
transaction**. Help desks, billing systems, CRMs, identity systems, and runtime authorization
remain systems outside that boundary.

## Why this exists

Modern support platforms can generate responses and call tools. The harder operational problem
starts when a high-impact action is approved but the provider response is delayed, ambiguous,
retried, lost, or later changes state. A support team still needs to answer:

- Which evidence and policy justified this action?
- What exact external resource and action were approved?
- Was an external side effect already attempted?
- Can a retry duplicate the customer impact?
- Does the provider confirm a terminal outcome now?
- Can an asynchronous provider event be authenticated and deduplicated?
- Is the support case actually resolved after the action?

ResolveOps makes those questions first-class workflow state instead of leaving them in logs or
agent traces.

## Current capabilities

- one canonical analysis transaction for an exact support-case replay, with conflicting reuse of
  the same ticket ID failing closed;
- atomic ticket + analysis + canonical claim + audit persistence at the application ingestion
  boundary;
- visible evidence provenance with freshness, approval, and content-integrity checks;
- deterministic business policy separated from response generation;
- refund proposals bound to one explicit billing-system payment identity and normalized payment
  snapshot digest rather than to a customer or heuristically selected charge;
- exact billing lookup identity checks plus required explicit refunded amount, refundability, and
  provider status in normalized payment snapshots—no optimistic financial-state defaults;
- ownership, currency, refundability, and remaining-refundable checks before a refund proposal is
  reviewable, plus payment-state revalidation at approval time;
- conservative refund-amount extraction that refuses to guess among distinct explicit money
  values in one customer message;
- a narrow Stripe transaction adapter for exact **non-Connect USD Charge refunds**, with explicit
  API version/credential injection, stable idempotency identity, exact refund reconciliation, and
  fail-closed ambiguous-response replay limits;
- explicit plan-change and cancellation proposals;
- mandatory human review for destructive actions in the current development line;
- one atomic review transition that also claims the approved execution intent;
- stable, non-sensitive idempotency keys for external action attempts;
- explicit execution states: `pending`, `in_flight`, `submitted`, `succeeded`, `failed`, `unknown`;
- a durable pre-call `in_flight` transition so process termination cannot erase that a provider
  interaction may have started;
- persisted uncertain execution state that survives process restart;
- reconciliation as a separate, auditable operation;
- append-only post-action outcome observations that do not rewrite terminal command history;
- authenticated Stripe refund-webhook processing that verifies the raw-body HMAC/timestamp and
  test/live mode before using an event as an outcome trigger;
- explicit overlapping endpoint-secret validation for Stripe rotation windows without disabling
  signature verification;
- webhook refund-to-execution binding plus an exact provider-current read instead of trusting the
  webhook payload's embedded status;
- atomic Stripe event-ID claims bound to immutable event identity so concurrent/retried delivery
  commits at most one outcome fact and conflicting ID reuse fails closed;
- a dedicated minimal Stripe webhook FastAPI ingress, separate from the broader reference support
  API;
- hash-chained audit evidence over analyses, approvals, execution transitions, and outcome
  observations;
- SQLite and in-memory persistence, plus a specialized SQLite webhook store for durable event
  replay protection;
- support-outcome and execution-integrity metrics;
- CLI workflows and optional FastAPI adapters;
- ports that keep vendor billing/execution and AgentGuard-style runtime authorization outside the
  domain.

The default demo remains offline and deterministic and requires no API key or hidden LLM dependency.
The Stripe adapter and webhook boundary are optional integration paths; deterministic CI proves our
contracts, not Stripe's real provider behavior.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,web]'
resolveops demo
pytest
```

Run the optional reference support API adapter:

```bash
resolveops serve
```

The dedicated Stripe webhook app is intentionally composed separately from that reference support
API so financial ingress can receive a narrower deployment/security boundary.

## Architecture

ResolveOps remains a modular monolith with hexagonal boundaries:

```text
domain → application → ports ← adapters
```

The domain layer has no FastAPI, SQLite, vendor SDK, or network dependency. Vendor-specific
code belongs behind ports; runtime authorization may be delegated to AgentGuard rather than
reimplemented here.

See [Architecture](docs/architecture.md) and [Integration contracts](docs/integration-contracts.md).

## Safety and integrity boundary

High-impact actions are deliberately constrained:

- identical support-case replays converge on one canonical analysis transaction;
- reuse of the same ticket ID with changed content fails closed rather than silently creating a
  new resolution transaction;
- model output cannot override deterministic business policy;
- stale, revoked, future-dated, or mutated evidence fails closed for approval;
- a refund requires an explicit payment reference and cannot be targeted by customer-level or
  latest-payment heuristics;
- the billing reader must return the exact requested payment identity, and safety-relevant payment
  state is required rather than defaulted;
- refund ownership, current normalized payment state, currency, and remaining refundable amount
  are checked before approval/execution;
- distinct explicit refund-related money values are treated as ambiguous rather than guessed;
- ambiguous action parameters fail closed;
- destructive actions require explicit human review in the current development line;
- approval and execution intent are persisted together so a process crash cannot lose the fact
  that an approved action is due for execution;
- every external adapter invocation is first persisted as an `in_flight` attempt;
- an external call uses a stable idempotency key;
- transport ambiguity is represented as `unknown`, never silently collapsed into failure;
- non-terminal executions can be reconciled after restart;
- Stripe execution is deliberately restricted to the currently evidenced resource/currency shape
  rather than pretending Connect or broad-currency semantics are generic;
- authenticated Stripe events must pass raw-body signature/timestamp/livemode validation and bind
  to one known refund execution;
- a signed webhook is only an authenticated trigger: ResolveOps re-reads the exact provider refund
  before appending the current outcome observation;
- Stripe event identities are atomically claimed before an outcome observation is committed;
- analysis, approval, execution, and outcome records are bound into the hash-chained audit log.

This is not a complete production security boundary. Real Stripe test-mode transaction/webhook
evidence, deployment identity and authorization, secret storage/distribution/retirement
orchestration, infrastructure rate limiting/request-size enforcement, tenant isolation, and runtime
credential/action authorization remain production gates.

See [Security model](docs/security-model.md) and [Limitations](docs/limitations.md).

## Validation

The last frozen engineering baseline is **0.1.0rc2**. Its GitHub CI evidence covers Python
3.11, 3.12, and 3.13, 72 tests, and 96.11% branch-aware coverage. That evidence predates the
post-RC execution-integrity and integration work on `main` and must not be used as validation for
later behavior-changing commits.

Every new pull request is revalidated by the repository CI matrix. A new release-candidate
validation record will be frozen only after the real integration path and its failure modes are
exercised.

See [Release validation](docs/release-validation.md).

## Product boundary

ResolveOps owns:

- support-case identity and canonical analysis ingestion;
- support-case evidence assembly and applicability;
- support-specific deterministic policy;
- explicit resource-bound action proposals and human review;
- support workflow state transitions;
- execution intent, idempotency, reconciliation, and post-action verification;
- authenticated support-specific outcome triggers and event replay protection;
- support outcome measurement and auditability.

ResolveOps does **not** own:

- response-model routing or inference economics;
- generic behavioral evaluation/regression testing;
- runtime credential binding or authorization enforcement;
- generic agent orchestration;
- RFP/security-questionnaire governance;
- a help-desk, CRM, billing ledger, or identity system of record;
- a broad connector or webhook marketplace.

The next integration milestone is deliberately **provider evidence**, not connector breadth: retain
real Stripe test-mode transaction and webhook-delivery evidence for the already narrow refund path,
then validate the pilot economics before expanding scope.

## Documentation

- [Architecture](docs/architecture.md)
- [Integration contracts](docs/integration-contracts.md)
- [Stripe refund integration](docs/stripe-refund-integration.md)
- [Security model](docs/security-model.md)
- [Limitations](docs/limitations.md)
- [Product metrics](docs/product-metrics.md)
- [Roadmap](docs/roadmap.md)
- [Release validation](docs/release-validation.md)
- [Release process](docs/releasing.md)

## Status

**Development after the 0.1.0rc2 frozen baseline. Production readiness is not claimed.**

A stable release requires retained real provider evidence, credible transaction/webhook failure-mode
validation, prospective product evidence, deployment authorization, and release-governance gates in
addition to green CI.

Licensed under the Apache License 2.0.
