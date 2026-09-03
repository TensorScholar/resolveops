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
idempotency, explicit refund payment-target binding, and a deterministic Stripe refund transaction
slice with append-only post-action outcome verification. These changes are not part of the frozen
`0.1.0rc2` validation record.

## Next milestones

1. finish and merge the narrow non-Connect USD Stripe Charge refund adapter behind the existing
   `BillingReader`, `ActionExecutor`, and action-outcome verification contracts without widening
   refund targeting into customer-level payment search;
2. validate provider authentication, current-state enforcement, idempotency retention, timeout,
   ambiguous-response, refund retrieval, lifecycle reconciliation, and partial-refund behavior in
   Stripe test mode, retaining evidence that distinguishes provider facts from deterministic mocks;
3. add an authenticated webhook ingestion boundary with signature verification and replay handling
   before asynchronous provider events can affect production outcome state;
4. run one narrowly scoped pilot using sanitized, synthetic, or customer-owned data and measure
   successful-resolution rate, reconciliation burden, post-action verification lag, repeat-contact
   proxy, and cost per successful resolution;
5. add the deployment identity/authorization boundary required by the connector, delegating runtime
   credential/action binding to AgentGuard where appropriate rather than duplicating it;
6. address reliability and product-quality findings from the pilot;
7. protect `main` with required CI/review governance, rehearse the release path, freeze a new
   release-candidate validation record, and cut a stable `0.1.0` only when the external evidence
   supports it.

## Expansion gates

Broader provider behavior is earned through evidence rather than assumed:

- additional Stripe currencies require explicit amount-representation and lifecycle tests;
- Stripe Connect refunds require separate application-fee/transfer-reversal semantics and evidence;
- additional billing providers must fit the support-resolution transaction contract without
  introducing a generic connector framework;
- autonomous destructive actions remain out of scope until product evidence and runtime controls
  justify a different risk posture.

## Explicitly deferred

- hosted multi-tenant control plane;
- multi-region deployment;
- broad connector catalog;
- generic plugin marketplace;
- autonomous destructive actions;
- expansion into a general-purpose agent platform.
