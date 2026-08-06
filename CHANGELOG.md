# Changelog

## 0.1.0rc2

- Enforced policy again at review time and blocked ambiguous or evidence-deficient actions.
- Added atomic one-review-per-analysis claims to prevent approval and execution replay.
- Serialized SQLite audit appends and converted corrupt persisted payloads into explicit
  integrity failures.
- Rejected future-dated evidence and stopped treating arbitrary unmarked numbers as money.
- Hardened the mock executor, API validation/error mapping, Docker data path, CI release
  gates, architecture checks, and secret scanning.
- Moved the composition root outside the application layer and added adversarial,
  concurrency, persistence-integrity, and API tests.
- Bound analyses and full knowledge-article content to audit evidence, removed the
  unsupported automatic-action mode, and added replay checks against retained audit history.

## 0.1.0rc1

- Added evidence-grounded support analysis.
- Added deterministic action policy and human review.
- Added SQLite and in-memory stores.
- Added audit verification, outcome metrics, evaluation, CLI, and optional API.
- Added tests, CI, release evidence, threat model, and Codex handoff.
