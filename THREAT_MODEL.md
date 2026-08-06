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
- explicit state transitions and one atomic review claim per analysis;
- hash-chained audit events;
- serialized SQLite audit appends and fail-closed persisted-model decoding;
- opaque external references in the mock adapter;
- SQLite WAL and transaction boundaries.

## Residual risk

The hash chain detects mutation inside the retained log but cannot independently detect
tail truncation without an externally stored head. A privileged database writer can also
rewrite the complete chain and recompute hashes; external anchoring or signing is required
for a stronger boundary. An external action may complete and
then fail to return a result; ResolveOps records that outcome as unknown and blocks blind
replay, but manual reconciliation is still required. The package does not implement user
authentication, tenant isolation, or production credentials.
