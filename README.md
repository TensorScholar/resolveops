# ResolveOps

[![CI](https://github.com/TensorScholar/resolveops/actions/workflows/ci.yml/badge.svg)](https://github.com/TensorScholar/resolveops/actions/workflows/ci.yml)

**Evidence-grounded customer support operations with policy-gated actions, human approval, and tamper-evident audit trails.**

ResolveOps is a compact reference implementation for support workflows where generating a response is only one part of the job. It combines customer context, approved knowledge, deterministic policy, explicit action proposals, human review, execution records, and measurable outcomes in one inspectable system.

```text
ticket
  ↓
customer context + approved knowledge
  ↓
evidence-grounded analysis
  ↓
deterministic policy decision
  ↓
action proposal
  ↓
human approval when required
  ↓
execution + outcome + audit evidence
```

## What it demonstrates

- retrieval with visible source metadata and evidence freshness checks;
- fail-closed behavior when evidence is missing, stale, revoked, or ambiguous;
- deterministic business policy separated from response generation;
- explicit refund, plan-change, and cancellation proposals instead of hidden tool calls;
- mandatory human review for destructive actions in this release;
- replay-resistant review and execution state transitions;
- hash-chained audit evidence with persisted analysis and citation digests;
- SQLite or in-memory persistence;
- outcome metrics, including cost per successful resolution;
- fixture-based evaluation, CLI workflows, and an optional FastAPI adapter;
- an `ActionExecutor` port for integrating a production authorization/execution boundary.

The default implementation is offline and deterministic. It requires no API key and no hidden LLM dependency.

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

ResolveOps is a modular monolith with hexagonal boundaries:

```text
domain → application → ports ← adapters
```

The domain layer has no FastAPI, SQLite, vendor SDK, or network dependency. Adapter selection happens at the composition root.

```text
src/resolveops/
├── domain/        # models, policy, audit rules
├── application/   # use-case orchestration
├── ports/         # integration contracts
├── adapters/      # persistence and execution adapters
├── web/           # optional FastAPI adapter
├── bootstrap.py   # composition root
├── cli.py
└── demo.py
```

See [Architecture](docs/architecture.md) and the [ADRs](docs/adr/).

## Safety model

High-impact actions are deliberately constrained:

- policy is deterministic and does not consume model instructions;
- evidence must be approved and current;
- ambiguous amounts or action targets fail closed;
- destructive actions require explicit review;
- one analysis cannot be approved or executed repeatedly;
- persisted analyses and retrieved evidence are bound into audit records;
- external execution failures are recorded without blind replay.

The audit chain is tamper-evident, not tamper-proof. Stronger deployment boundaries require external audit-head anchoring, authentication, authorization, tenant isolation, provider idempotency, and production secret management.

See [Security model](docs/security-model.md), [Security policy](SECURITY.md), and [Limitations](docs/limitations.md).

## Validation

The current `0.1.0rc2` candidate has been validated on the canonical GitHub `main` commit across Python 3.11, 3.12, and 3.13. The final CI matrix passes formatting, linting, strict type checking, architecture checks, secret/static-security checks, schema consistency, the full test suite, branch coverage, the offline demo, and dependency auditing.

The validated test suite contains **72 tests** with **96.11% branch-aware coverage** against an 85% required threshold.

Detailed scope, reproduced failures, remediation, residual risks, and release evidence are recorded in [Release validation](docs/release-validation.md).

## Product boundary

Included in this release candidate:

- evidence-grounded ticket analysis;
- approved knowledge citations;
- deterministic triage and action policy;
- human-gated refund, plan-change, and cancellation flows;
- mock execution;
- SQLite and in-memory persistence;
- audit verification;
- evaluation fixtures and outcome metrics;
- CLI and optional FastAPI interfaces.

Not included:

- live CRM, billing, email, or help-desk connectors;
- production identity, authorization, or tenant isolation;
- a credential vault or production secret-management boundary;
- active-active or multi-region persistence;
- autonomous destructive actions;
- a hosted multi-tenant control plane.

## Documentation

Start with the [documentation index](docs/README.md).

- [Architecture](docs/architecture.md)
- [Integration contracts](docs/integration-contracts.md)
- [Security model](docs/security-model.md)
- [Limitations](docs/limitations.md)
- [Product metrics](docs/product-metrics.md)
- [Roadmap](docs/roadmap.md)
- [Release validation](docs/release-validation.md)
- [Release process](docs/releasing.md)
- [Changelog](CHANGELOG.md)

## Status

**ResolveOps 0.1.0rc2 is an engineering release candidate for demonstration and external review.** The repository has strong automated validation, but the current implementation is not a complete production deployment boundary.

Licensed under the Apache License 2.0.