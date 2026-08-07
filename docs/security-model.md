# Security model

ResolveOps is designed around a narrow integrity boundary: customer-support analysis may propose high-impact actions, but deterministic policy, evidence checks, review state, and audit evidence constrain whether those actions can proceed.

## Protected assets

- customer context;
- approved knowledge and its provenance;
- analysis and policy decisions;
- action proposals and approvals;
- execution records and outcomes;
- audit evidence.

## Primary threats

1. **Instruction or prompt injection** — ticket text attempts to override policy or execution rules.
2. **Unsupported or stale evidence** — missing, revoked, expired, replaced, future-dated, or changed knowledge supports an unsafe answer or action.
3. **Ambiguous action parameters** — an amount, target plan, or destructive action is inferred without explicit support.
4. **Approval misuse or replay** — an analysis is approved, rejected, or executed more than once or after its integrity boundary changes.
5. **Persistence corruption or concurrency faults** — stored models are malformed or concurrent audit appends collide.
6. **Audit mutation** — retained events are edited, reordered, or truncated.
7. **External side-effect uncertainty** — an external action succeeds but the process fails before the result is recorded.
8. **Sensitive-data leakage** — logs, fixtures, or repository content expose credentials or customer information.
9. **Boundary misuse** — SQLite or the mock executor is treated as a production-scale coordination or authorization system.

## Current controls

- business policy is deterministic Python and does not consume model instructions;
- retrieval accepts only approved and temporally valid knowledge;
- retrieved citations include content digests so silent evidence mutation can be detected;
- refund amounts and plan targets must be explicit rather than inferred from arbitrary numbers;
- destructive actions are human-gated in this release;
- review uses an atomic one-review claim and retained audit history to block replay;
- persisted `AnalysisResult` content is bound into audit evidence;
- audit events form a hash chain;
- SQLite audit sequence allocation is serialized with transactional locking;
- malformed persisted models fail closed as integrity errors;
- external-executor exceptions are recorded as unknown outcomes and blind replay is blocked;
- the domain layer is isolated from FastAPI, SQLite, network clients, and vendor SDKs;
- secret and static-security checks run in CI.

## Implementation risk register

| Risk | Failure mode | Current mitigation | Evidence |
|---|---|---|---|
| Unsupported answer | Response invents policy | evidence threshold and escalation | citation/adversarial tests |
| Prompt injection | Ticket text tries to override rules | deterministic policy outside generated content | adversarial tests |
| Stale evidence | Old or changed article supports an action | approval, expiry, age, replacement, and digest checks | stale/mutation tests |
| Action ambiguity | Refund amount or target is missing | fail closed until explicit | ambiguity tests |
| Excessive refund | Proposal exceeds policy ceiling | deterministic deny before review | policy boundary tests |
| Approval replay | Analysis is reviewed or executed repeatedly | atomic review claim plus audit-history replay checks | replay/concurrency tests |
| External tool failure | Side effect status is uncertain | record unknown outcome; block blind retry | executor tests |
| Audit mutation | Event is edited or reordered | hash chain; external anchoring recommended | tamper tests |
| Persistence corruption | Stored JSON violates model contract | integrity error instead of raw decode/validation leakage | persistence tests |
| Concurrency | Duplicate approval or audit sequence | atomic review claim and serialized SQLite append | concurrency tests |
| PII/secret leakage | Logs or repository content expose sensitive values | constrained audit payloads plus repository scanning | secret/security checks |
| SQLite misuse | Multiple writers/replicas diverge | explicit single-node boundary | architecture/limitations review |
| Vendor lock-in | SDK concerns spread through domain | ports/adapters and offline baseline | architecture check |
| Scope creep | Project becomes a generic agent platform | narrow workflow and roadmap | project review |

## Residual risks

The current controls do not make ResolveOps a complete production security boundary.

- The audit log is **tamper-evident, not tamper-proof**. A privileged database writer can rewrite the complete retained chain and recompute hashes. Tail truncation cannot be detected independently without an externally anchored head.
- SQLite is a single-node persistence and coordination boundary. It is not intended for active-active replicas or multi-region operation.
- A process can terminate after an external side effect but before its result is persisted. ResolveOps records uncertain outcomes when observed and blocks blind replay, but real integrations still require provider idempotency, reconciliation, and operational recovery procedures.
- The API does not implement production authentication, authorization, tenant isolation, rate limiting, or secret management.
- The bundled executor is a mock adapter, not a production payment or subscription connector.
- The deterministic response generator and lexical retrieval are inspectable baselines, not evidence of real-world language-model or retrieval quality on customer data.

## Production boundary

Before connecting ResolveOps to live customer or billing systems, introduce a dedicated authorization and integration boundary with authenticated identities, tenant isolation, scoped credentials, provider-side idempotency, timeouts, reconciliation, observability, incident response, and externally anchored audit evidence where required.

For vulnerability reporting, see [`../SECURITY.md`](../SECURITY.md). For product-level exclusions, see [`limitations.md`](limitations.md).