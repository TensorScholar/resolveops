# Limitations

- lexical retrieval is intentionally small and inspectable;
- no live CRM, billing, email, or help-desk integration;
- no identity provider or multi-tenant authorization;
- SQLite is single-node;
- the deterministic generator is a baseline, not a language model;
- the optional web API is an adapter, not a complete product UI;
- no production claim is made;
- no externally anchored or signed audit head; a privileged database writer is outside the
  current integrity boundary;
- no safe autonomous-action path; all destructive actions are human-gated.
