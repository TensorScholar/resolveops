# Limitations

- no live CRM, billing, email, or help-desk integration yet;
- refund proposals do not yet bind to a real payment/charge object from a system of record;
- case-level canonicalization is keyed by `Ticket.id` and the exact persisted ticket payload;
  ResolveOps treats a repeated ID with changed content as an integrity conflict rather than a
  mutable case revision, so an upstream integration that edits cases in place needs an explicit
  immutable event/version identity contract;
- concurrent duplicate ingestion can still repeat classification/retrieval/generation work
  before one canonical analysis wins the store transaction; persistence and downstream action
  identity remain deduplicated, but duplicate model/provider compute is not yet suppressed;
- provider-specific retry windows, webhook authenticity, and reconciliation semantics are not
  validated until the first real adapter exists;
- legacy pre-lifecycle SQLite databases with ambiguous execution history are rejected at startup
  rather than guessed into the new state model; current-format execution rows can be backfilled
  into the execution-claim index only after their approval/execution identity is verified;
- legacy SQLite databases can backfill one audited analysis per ticket into the canonical
  analysis-claim index; multiple historical analyses for one ticket are rejected because choosing
  a canonical resolution transaction would be ambiguous;
- lexical retrieval is intentionally small and inspectable;
- no identity provider or multi-tenant authorization boundary;
- SQLite is a single-node persistence and coordination boundary;
- the deterministic generator is a baseline, not a language model;
- the optional web API is an adapter, not a complete product UI;
- no production or customer-impact claim is made;
- the audit chain is tamper-evident rather than independently tamper-proof; a privileged writer
  remains outside the current integrity boundary;
- destructive actions remain human-gated.

ResolveOps now prevents an identical support-case replay from creating a second internal
resolution transaction: one `Ticket.id` is bound to one exact ticket payload and one canonical
analysis. That internal guarantee does **not** establish idempotency at an external provider.
Provider-level idempotency and reconciliation must still be proven by the specific adapter and
provider contract before a live destructive-action connector is enabled.
