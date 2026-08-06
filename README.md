# ResolveOps

**Evidence-grounded customer support operations with approval-gated actions and measurable outcomes.**

ResolveOps is not a generic chatbot. It is a compact, inspectable reference system for the workflow companies actually need:

```text
ticket → customer context → approved evidence → draft → policy decision
       → human approval when necessary → action → outcome and cost measurement
```

## Why this project exists

Most support demos stop after generating text. ResolveOps demonstrates the harder product work:

- retrieval with visible source metadata;
- fail-safe escalation when evidence is missing or stale;
- explicit action proposals rather than hidden tool calls;
- mandatory human review for destructive actions by default;
- deterministic business policy separated from the response generator;
- append-only audit evidence;
- outcome metrics, including cost per successful resolution;
- an export contract for InferenceLedger;
- an `ActionExecutor` port that can be wrapped by a production authorization adapter.

The default implementation is offline and its decision path is deterministic. Generated
identifiers and timestamps are intentionally unique, so complete JSON output is not
byte-for-byte reproducible. It does not require an API key and does not pretend to be
production-ready.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,web]'
resolveops demo
pytest
```

Run the API:

```bash
resolveops serve
```

## Product boundary

Included in v0.1:

- ticket analysis;
- customer context;
- approved knowledge articles and citations;
- deterministic triage;
- refund, plan-change, and cancellation proposals;
- review and mock execution;
- SQLite or in-memory persistence;
- hash-chained audit verification;
- outcome metrics and fixture-based evaluation;
- CLI and optional FastAPI adapter.

Explicitly not included:

- a live payment processor;
- a credential vault;
- autonomous refunds without configured policy;
- a hosted multi-tenant control plane;
- a hidden LLM dependency;
- claims of production readiness.

## Architecture

ResolveOps uses a modular monolith with hexagonal boundaries:

```text
domain → application → ports ← adapters
```

The domain has no FastAPI, SQLite, vendor SDK, or network dependency. The composition root chooses adapters.

See [docs/architecture.md](docs/architecture.md), [THREAT_MODEL.md](THREAT_MODEL.md), and
[docs/product-metrics.md](docs/product-metrics.md).

## Demo result

The bundled demo analyzes a duplicate-charge request, cites an approved refund policy,
requires human review, executes a mock refund after approval, records the outcome, and
verifies the audit chain.

## Status

**Version 0.1.0rc2 is an engineering release candidate for demonstration and external
review. It is not production-ready.**
