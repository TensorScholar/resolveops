# Limitations

- no live CRM, billing, email, or help-desk integration yet;
- refund proposals now bind to an explicit normalized payment snapshot, but the only billing
  implementation in the repository is an in-memory reference adapter; there is no live
  payment/charge system-of-record connector yet;
- case-level canonicalization is keyed by `Ticket.id` and the exact persisted ticket payload;
  ResolveOps treats a repeated ID with changed content as an integrity conflict rather than a
  mutable case revision, so an upstream integration that edits cases in place needs an explicit
  immutable event/version identity contract;
- an exact replay returns the already-created resolution transaction and intentionally does not
  regenerate it from mutable customer-profile or billing state; billing state is revalidated at
  approval, while upstream authorization and mutable case revisions require their own integration
  contracts rather than changing replay semantics;
- approval-time payment verification does not eliminate the final time-of-check/time-of-use race
  before an external financial provider call; a production adapter must enforce the provider's
  current refund constraints as part of submission;
- refund reconciliation intentionally cannot require the current payment snapshot to equal the
  pre-side-effect digest because a successful or partially accepted refund can itself change the
  payment's refunded amount or status;
- concurrent duplicate ingestion can still repeat classification/retrieval/generation work
  before one canonical analysis wins the store transaction; persistence and downstream action
  identity remain deduplicated, but duplicate model/provider compute is not yet suppressed;
- provider-specific retry windows, webhook authenticity, and reconciliation semantics are not
  validated until the first real adapter exists;
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
- the optional web API is an adapter, not a complete product UI;
- no production or customer-impact claim is made;
- the audit chain is tamper-evident rather than independently tamper-proof; a privileged writer
  remains outside the current integrity boundary;
- destructive actions remain human-gated.

ResolveOps prevents an identical support-case replay from creating a second internal resolution
transaction: one `Ticket.id` is bound to one exact ticket payload and one canonical analysis. For
refunds, the proposed action is additionally bound to one explicit payment identity and payment
snapshot digest before review. These internal guarantees do **not** establish idempotency or
financial correctness at an external provider. Provider-level idempotency, current-state
validation, reconciliation, and authentication must still be proven by the specific adapter and
provider contract before a live destructive-action connector is enabled.
