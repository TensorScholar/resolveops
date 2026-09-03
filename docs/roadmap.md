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

Post-RC development has added crash-safe action lifecycle/reconciliation, canonical case-ingestion
idempotency, and explicit refund payment-target binding. These changes are not part of the frozen
`0.1.0rc2` validation record.

## Next milestones

1. implement one live refund adapter behind the existing `BillingReader` and `ActionExecutor`
   contracts without widening refund targeting into customer-level payment search;
2. validate provider authentication, current-state enforcement, idempotency retention, timeout,
   ambiguous-response, webhook/reconciliation, and partial-refund behavior against that adapter;
3. run one narrowly scoped pilot using sanitized, synthetic, or customer-owned data;
4. add the deployment identity/authorization boundary required by the connector, delegating
   runtime credential/action binding to AgentGuard where appropriate;
5. address reliability and product-quality findings from the pilot;
6. freeze a new release-candidate validation record and cut a stable `0.1.0` only when the
   external evidence supports it.

## Explicitly deferred

- hosted multi-tenant control plane;
- multi-region deployment;
- broad connector catalog;
- generic plugin marketplace;
- autonomous destructive actions;
- expansion into a general-purpose agent platform.
