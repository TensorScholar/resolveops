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
idempotency, explicit refund payment-target binding, and a narrow Stripe Charge refund transaction
adapter with separate append-only post-action outcome observations. These changes are not part of
the frozen `0.1.0rc2` validation record.

## Next milestones

1. validate the Stripe Charge/refund transaction against Stripe **test mode**, including provider
   authentication/API-version pinning, successful partial refund, provider-current over-refund
   rejection, same-key ambiguous-response recovery, and refund lifecycle retrieval;
2. add authenticated Stripe webhook ingestion only after signature verification, replay handling,
   event-to-execution identity binding, and failure-path tests are proven;
3. run one narrowly scoped support-operations pilot using sanitized, synthetic, or customer-owned
   case data and test/sandbox financial operations;
4. add the deployment identity/authorization boundary required by the connector, delegating
   runtime credential/action binding to AgentGuard where appropriate;
5. address reliability and product-quality findings from the pilot;
6. protect `main` with required CI/review governance, rehearse the release path, freeze a new
   release-candidate validation record, and cut stable `0.1.0` only when the external evidence
   supports it.

## Explicitly deferred

- hosted multi-tenant control plane;
- multi-region deployment;
- broad connector catalog;
- generic plugin marketplace;
- autonomous destructive actions;
- expansion into a general-purpose agent platform.
