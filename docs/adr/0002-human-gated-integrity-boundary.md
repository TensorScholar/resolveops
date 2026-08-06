# ADR 0002: Human-gated actions and integrity-bound review

- Status: Accepted
- Date: 2026-08-06

## Context

The original policy model exposed automatic-action settings, but the service had no safe,
idempotent automatic execution transaction. Review also trusted persisted analysis and
citation metadata without binding the complete objects to retained audit evidence.

## Decision

For `0.1.0rc2`:

1. every destructive action requires a human review;
2. unsupported automatic-action settings are removed;
3. analysis content is hashed into the `ticket.analyzed` audit event;
4. each citation carries a digest of the complete source article;
5. review verifies the audit chain, analysis digest, current article digest, policy, and
   one-review claim before invoking the executor;
6. executor exceptions produce an unknown outcome and are never blindly retried.

## Consequences

This is safer and makes the release boundary honest. It does not create distributed
transactions with external providers. Production adapters still require provider-side
idempotency and reconciliation. The local hash chain does not defend against a privileged
attacker who can rewrite the entire database and recompute every hash.
