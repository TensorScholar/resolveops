# Limitations

- no live CRM, email, or help-desk integration yet;
- a deterministic network-capable Stripe adapter now exists for exact non-Connect USD Charge
  refunds, but retained real Stripe test-mode evidence is still incomplete: the connected test
  account currently has no Charge fixture and the available connector surface cannot create the
  required PaymentIntent/Charge fixture;
- refund proposals bind to an explicit normalized payment snapshot and never discover a payment by
  customer/latest-payment heuristics;
- case-level canonicalization is keyed by `Ticket.id` and the exact persisted ticket payload;
  ResolveOps treats a repeated ID with changed content as an integrity conflict rather than a
  mutable case revision, so an upstream integration that edits cases in place needs an explicit
  immutable event/version identity contract;
- an exact replay returns the already-created resolution transaction and intentionally does not
  regenerate it from mutable customer-profile or billing state; billing state is revalidated at
  approval, while upstream authorization and mutable case revisions require their own integration
  contracts rather than changing replay semantics;
- approval-time payment verification does not eliminate the final time-of-check/time-of-use race
  before an external financial provider call; the Stripe adapter relies on provider-current
  submission constraints and must still be proven against real test-mode behavior;
- refund reconciliation intentionally cannot require the current payment snapshot to equal the
  pre-side-effect digest because a successful or partially accepted refund can itself change the
  payment's refunded amount or status;
- concurrent duplicate ingestion can still repeat classification/retrieval/generation work before
  one canonical analysis wins the store transaction; persistence and downstream action identity
  remain deduplicated, but duplicate model/provider compute is not yet suppressed;
- deterministic tests cover Stripe request identity, idempotency/reconciliation logic, and webhook
  security semantics, but they do not establish the provider's real idempotency-retention,
  lifecycle, retry, or event-delivery behavior;
- the authenticated Stripe webhook boundary accepts only refund outcome triggers, verifies raw-body
  HMAC/timestamp/livemode, binds a refund to exactly one execution, performs a provider-current read,
  and atomically claims event IDs before outcome commit; this is not a generic webhook framework;
- the webhook processor currently accepts one configured endpoint secret. It can validate multiple
  `v1` signatures for that secret in one header, but first-class overlapping old/new endpoint-secret
  rotation is not implemented;
- application-level webhook body-size checking occurs after the ASGI server receives the body;
  production deployment still needs upstream request-size enforcement, rate limiting/WAF, network
  policy, deployment identity, authorization, and tenant routing;
- a valid Stripe event can race persistence of the corresponding refund execution; the dedicated
  ingress returns `503` so Stripe may retry, but real provider retry/delivery behavior is still an
  external evidence gate;
- provider-current lookup during webhook processing can fail or time out; ResolveOps records an
  append-only `unknown` observation rather than trusting the signed payload's embedded status;
- legacy pre-lifecycle SQLite databases with ambiguous execution history are rejected at startup
  rather than guessed into the new state model; current-format execution rows can be backfilled
  into the execution-claim index only after their approval/execution identity is verified;
- pre-canonical analysis history can be backfilled only when its audit event already binds both
  the exact ticket payload digest and analysis digest; older `ticket.analyzed` events that lack
  `ticket_hash`, or multiple historical analyses for one ticket, are rejected at startup rather
  than guessed into a canonical resolution transaction;
- legacy refund action payloads that lack payment resource binding remain decodable for
  migration/forensics, but they are not executable or automatically reconcilable;
- lexical retrieval is intentionally small and inspectable;
- no identity provider or multi-tenant authorization boundary;
- SQLite is a single-node persistence and coordination boundary;
- the deterministic generator is a baseline, not a language model;
- the optional support API and dedicated webhook app are adapters, not a complete product UI or
  production deployment boundary;
- no production or customer-impact claim is made;
- the audit chain is tamper-evident rather than independently tamper-proof; a privileged writer
  remains outside the current integrity boundary;
- destructive actions remain human-gated.

ResolveOps prevents an identical support-case replay from creating a second internal resolution
transaction: one `Ticket.id` is bound to one exact ticket payload and one canonical analysis. For
refunds, the proposed action is additionally bound to one explicit payment identity and payment
snapshot digest before review. Stripe execution uses one stable idempotency identity, and webhook
event IDs are atomically deduplicated before outcome facts are committed. These internal guarantees
do **not** prove the external provider's financial correctness, idempotency retention, or delivery
behavior. Those claims require retained Stripe test-mode evidence before live destructive-action
execution is enabled.
