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
            explicit action proposal
                    ↓
             human review if required
                    ↓
     durable execution claim + idempotency key
                    ↓
        provider execution / reconciliation
                    ↓
          verified support outcome + audit
```

The product boundary is intentionally narrow: ResolveOps owns the **support-resolution
transaction**. Help desks, billing systems, CRMs, identity systems, and runtime authorization
remain systems outside that boundary.

## Why this exists

Modern support platforms can generate responses and call tools. The harder operational problem
starts when a high-impact action is approved but the provider response is delayed, ambiguous,
retried, or lost. A support team still needs to answer:

- Which evidence and policy justified this action?
- What exact action was approved?
- Was an external side effect already attempted?
- Can a retry duplicate the customer impact?
- Does the provider confirm a terminal outcome?
- Is the support case actually resolved after the action?

ResolveOps makes those questions first-class workflow state instead of leaving them in logs or
agent traces.

## Current capabilities

- visible evidence provenance with freshness, approval, and content-integrity checks;
- deterministic business policy separated from response generation;
- explicit refund, plan-change, and cancellation proposals;
- mandatory human review for destructive actions in the current development line;
- one atomic review transition that also claims the approved execution intent;
- stable, non-sensitive idempotency keys for external action attempts;
- explicit execution states: `pending`, `submitted`, `succeeded`, `failed`, `unknown`;
- persisted uncertain execution state that survives process restart;
- reconciliation as a separate, auditable operation;
- hash-chained audit evidence over analyses and execution transitions;
- SQLite and in-memory persistence;
- support-outcome and execution-integrity metrics;
- CLI workflows and an optional FastAPI adapter;
- ports that keep vendor execution and AgentGuard-style runtime authorization outside the domain.

The default implementation remains offline and deterministic. It requires no API key and has no
hidden LLM dependency.

## Quick start

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,web]'
resolveops demo
pytest
```

Run the optional API adapter:

```bash
resolveops serve
```

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

- model output cannot override deterministic business policy;
- stale, revoked, future-dated, or mutated evidence fails closed for approval;
- ambiguous action parameters fail closed;
- destructive actions require explicit human review in the current development line;
- approval and execution intent are persisted together so a process crash cannot lose the
  fact that an approved action is due for execution;
- an external call uses a stable idempotency key;
- transport ambiguity is represented as `unknown`, never silently collapsed into failure;
- non-terminal executions can be reconciled after restart;
- execution records are bound into the hash-chained audit log.

This is not a complete production security boundary. Authentication, tenant isolation,
credential handling, provider-specific idempotency guarantees, webhook authenticity, and
runtime authorization belong to deployment/integration boundaries.

See [Security model](docs/security-model.md) and [Limitations](docs/limitations.md).

## Validation

The last frozen engineering baseline is **0.1.0rc2**. Its GitHub CI evidence covers Python
3.11, 3.12, and 3.13, 72 tests, and 96.11% branch-aware coverage. That evidence predates the
post-RC execution-integrity work on `main` and must not be used as validation for later
behavior-changing commits.

Every new pull request is revalidated by the repository CI matrix. A new release-candidate
validation record will be frozen only after the real integration path and its failure modes
are exercised.

See [Release validation](docs/release-validation.md).

## Product boundary

ResolveOps owns:

- support-case evidence assembly and applicability;
- support-specific deterministic policy;
- explicit action proposals and human review;
- support workflow state transitions;
- execution intent, idempotency, reconciliation, and post-action verification;
- support outcome measurement and auditability.

ResolveOps does **not** own:

- response-model routing or inference economics;
- generic behavioral evaluation/regression testing;
- runtime credential binding or authorization enforcement;
- generic agent orchestration;
- RFP/security-questionnaire governance;
- a help-desk, CRM, billing ledger, or identity system of record;
- a broad connector marketplace.

The next integration target is deliberately one narrow refund path, not a connector catalog.

## Documentation

- [Architecture](docs/architecture.md)
- [Integration contracts](docs/integration-contracts.md)
- [Security model](docs/security-model.md)
- [Limitations](docs/limitations.md)
- [Product metrics](docs/product-metrics.md)
- [Roadmap](docs/roadmap.md)
- [Release validation](docs/release-validation.md)
- [Release process](docs/releasing.md)

## Status

**Development after the 0.1.0rc2 frozen baseline. Production readiness is not claimed.**

A stable release requires a real external integration, credible retry/reconciliation behavior,
prospective product evidence, and release-governance gates in addition to green CI.

Licensed under the Apache License 2.0.
