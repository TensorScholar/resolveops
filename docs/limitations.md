# Limitations

- no live CRM, billing, email, or help-desk integration yet;
- refund proposals do not yet bind to a real payment/charge object from a system of record;
- provider-specific retry windows, webhook authenticity, and reconciliation semantics are not
  validated until the first real adapter exists;
- lexical retrieval is intentionally small and inspectable;
- no identity provider or multi-tenant authorization boundary;
- SQLite is a single-node persistence and coordination boundary;
- the deterministic generator is a baseline, not a language model;
- the optional web API is an adapter, not a complete product UI;
- no production or customer-impact claim is made;
- the audit chain is tamper-evident rather than independently tamper-proof; a privileged writer
  remains outside the current integrity boundary;
- destructive actions remain human-gated.

The execution lifecycle can preserve and reconcile ambiguous local state, but this alone does
not guarantee idempotency at an external provider. That guarantee must be established by the
specific adapter and provider contract.
