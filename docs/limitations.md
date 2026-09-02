# Limitations

- no live CRM, billing, email, or help-desk integration yet;
- refund proposals do not yet bind to a real payment/charge object from a system of record;
- repeated ingestion of the same support case is not yet deduplicated at the analysis boundary;
  a second analysis creates a distinct resolution transaction and therefore a distinct external
  idempotency key, so a production connector must not be enabled until case-level ingestion
  identity is enforced;
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

The execution lifecycle prevents blind replay of one approved resolution transaction and can
preserve/reconcile ambiguous local state. It does **not** yet provide case-ingestion idempotency,
and it does not by itself guarantee idempotency at an external provider. The next must be fixed
before a live action connector is enabled; the latter must be established by the specific
adapter and provider contract.
