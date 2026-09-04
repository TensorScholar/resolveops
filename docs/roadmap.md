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
idempotency, explicit refund payment-target binding, a deterministic non-Connect USD Stripe Charge
refund transaction slice with append-only post-action outcome verification, and an authenticated
Stripe refund-webhook boundary with atomic event replay/collision protection, retry-safe
provider-current verification, and overlapping endpoint-secret validation. These changes are not
part of the frozen `0.1.0rc2` validation record.

## Next milestones

1. obtain a controlled Stripe test-mode Charge fixture and retain provider evidence for exact Charge
   mapping, successful partial refund, current-state rejection, ambiguous-response idempotent
   recovery, exact refund retrieval, and lifecycle behavior;
2. exercise the authenticated webhook ingress against actual Stripe test-mode delivery and retries,
   retaining evidence for signature validation, duplicate delivery, execution binding, provider-
   current outcome refresh, event ordering, and retry behavior when local/provider state is
   temporarily unavailable;
3. add deployment-level secret storage/distribution/retirement orchestration, infrastructure
   request-size/rate limiting, network policy, identity/authorization, and tenant routing required
   for an enabled production ingress;
4. run one narrowly scoped pilot using sanitized, synthetic, or customer-owned data and measure
   successful-resolution rate, reconciliation burden, post-action verification lag, repeat-contact
   proxy, and cost per successful resolution;
5. add the destructive-action deployment identity/authorization boundary, delegating runtime
   credential/action binding to AgentGuard where appropriate rather than duplicating it;
6. address reliability and product-quality findings from the Stripe evidence run and pilot;
7. protect `main` with required CI/review governance, rehearse the release path, freeze a new
   release-candidate validation record, and cut a stable `0.1.0` only when the external evidence
   supports it.

## Expansion gates

Broader provider behavior is earned through evidence rather than assumed:

- additional Stripe currencies require explicit amount-representation and lifecycle tests;
- Stripe Connect refunds require separate application-fee/transfer-reversal semantics and evidence;
- additional billing providers must fit the support-resolution transaction contract without
  introducing a generic connector framework;
- additional webhook providers must fit the authenticated-event-trigger / provider-current-truth
  model rather than widening ResolveOps into a generic event bus;
- autonomous destructive actions remain out of scope until product evidence and runtime controls
  justify a different risk posture.

## Explicitly deferred

- hosted multi-tenant control plane;
- multi-region deployment;
- broad connector catalog;
- generic plugin marketplace;
- autonomous destructive actions;
- expansion into a general-purpose agent platform.
