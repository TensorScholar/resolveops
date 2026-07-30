# Threat model

## Protected assets

- customer context;
- approved knowledge;
- action proposals and approvals;
- action execution records;
- audit evidence.

## Primary threats

1. Prompt text attempts to override deterministic policy.
2. Stale or unapproved knowledge produces an unsafe answer.
3. A destructive action executes without human approval.
4. Approval or action state is replayed or mutated.
5. Audit events are edited or reordered.
6. Logs expose customer or credential data.
7. SQLite is used beyond its single-node coordination boundary.

## Current controls

- policy decisions are pure Python and do not consume model instructions;
- only approved, current articles are retrieved;
- destructive actions require approval by default;
- strict immutable Pydantic models;
- explicit state transitions;
- hash-chained audit events;
- opaque external references in the mock adapter;
- SQLite WAL and transaction boundaries.

## Residual risk

The hash chain detects mutation inside the retained log but cannot independently detect
tail truncation without an externally stored head. The package does not implement user
authentication, tenant isolation, or production credentials.
