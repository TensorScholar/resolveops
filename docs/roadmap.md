# Roadmap

ResolveOps is intentionally narrow. The roadmap prioritizes evidence from real review and integration work over breadth.

## Current release candidate

`0.1.0rc2` focuses on:

- deterministic offline workflow behavior;
- explicit contracts and fail-closed policy;
- human-gated high-impact actions;
- persistence and audit integrity;
- fixture-based evaluation and outcome metrics;
- CLI plus an optional API adapter;
- reproducible engineering and release validation.

## Next milestones

After external review:

1. run one narrowly scoped pilot using sanitized or synthetic customer-owned data;
2. implement one production-grade connector behind the existing ports;
3. add the identity, authorization, idempotency, reconciliation, and observability boundary required by that connector;
4. address reliability and product-quality findings from the pilot;
5. cut a stable `0.1.0` release when the evidence supports it.

## Explicitly deferred

- hosted multi-tenant control plane;
- multi-region deployment;
- broad connector catalog;
- generic plugin marketplace;
- autonomous destructive actions;
- expansion into a general-purpose agent platform.