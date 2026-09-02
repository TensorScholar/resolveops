# Security model

ResolveOps protects a narrow support-operations integrity boundary: untrusted customer text and
generated content may propose a high-impact action, but deterministic policy, evidence checks,
review state, durable execution intent, and reconciliation constrain whether the action can
become an external side effect.

## Protected assets

- customer and support-case context;
- approved knowledge and its provenance;
- analysis and policy decisions;
- action proposals and human approvals;
- execution identity, idempotency key, provider state, and reconciliation history;
- recorded support outcomes;
- audit evidence.

## Primary threats

1. **Instruction or prompt injection** — ticket text attempts to override policy or execution.
2. **Unsupported or stale evidence** — missing, revoked, expired, replaced, future-dated, or
   changed knowledge supports an unsafe action.
3. **Ambiguous action parameters** — an amount, target, or destructive operation is inferred
   without sufficient support.
4. **Approval replay** — an analysis is approved or rejected more than once.
5. **Lost execution intent** — a process crashes after approval but before the operation is
   durably represented.
6. **Duplicate external side effect** — a retry creates a second refund/change/cancellation.
7. **Ambiguous provider outcome** — the provider accepts the action but the response is lost.
8. **Stale non-terminal state** — an accepted provider operation later fails or requires action
   without ResolveOps reconciling it.
9. **Persistence or concurrency faults** — stored models are malformed, attempts race, or audit
   sequence allocation collides.
10. **Audit mutation** — retained events are edited, reordered, or truncated.
11. **Sensitive-data leakage** — logs, fixtures, keys, or repository content expose secrets or
   customer information.
12. **Boundary confusion** — ResolveOps is treated as a credential gateway, billing ledger, or
   horizontally scalable coordination service.

## Current controls

- deterministic business policy is isolated from generated response content;
- retrieval accepts only approved, temporally valid knowledge and binds article content digests;
- action parameters required by policy fail closed when ambiguous;
- destructive actions remain human-gated;
- persisted `AnalysisResult`, `Approval`, and `ActionExecution` content is bound into audit
  evidence;
- one review claim per analysis is enforced transactionally;
- an approved review and its initial `pending` execution claim are committed atomically with
  audit events;
- every execution receives a stable, non-sensitive idempotency key before any provider call;
- before every executor or reconciliation invocation, ResolveOps durably transitions the
  execution to `in_flight` and increments the attempt number;
- a returned provider result completes that same attempt, so attempt counts do not double-count
  the call/result pair;
- transport exceptions are represented as `unknown`, not as definitive failures;
- hard process termination after an external side effect leaves an auditable `in_flight`
  execution that can be reconciled after restart;
- a known external operation reference cannot silently change on a later transition;
- execution updates preserve immutable approved action identity and monotonic attempt ordering;
- persisted execution state is bound into the audit chain on every transition;
- reconciliation is explicit and adapter-owned; the application does not create a fresh action
  identity for an uncertain operation;
- SQLite audit allocation and review/execution transitions use serialized transactions;
- malformed or internally inconsistent persisted models fail closed as integrity errors;
- repository secret/static-security checks run in CI;
- the domain has no vendor SDK, network client, FastAPI, or SQLite dependency.

## Residual risks

These controls do not make ResolveOps a production authorization or financial system.

- A real provider must independently guarantee the idempotency and reconciliation behavior used
  by its adapter. The mock executor is only a deterministic reference implementation.
- Persisting `in_flight` before a provider call is conservative: a process can terminate after
  the local transition but before the request reaches the provider. ResolveOps therefore knows
  that an attempt may have started, not that the provider necessarily observed it.
- A provider operation can remain non-terminal (`in_flight`, `submitted`, or `unknown`) for an
  extended period. Production integrations need webhooks or scheduled reconciliation and an
  operator policy for stale state.
- The first real refund path still needs an explicit payment/charge target sourced from the
  billing system; a customer identifier alone is not a sufficient refund target.
- Webhook authenticity, replay protection, secret rotation, rate limiting, authenticated
  identities, authorization, and tenant isolation are not implemented by the reference API.
- The audit log is tamper-evident, not tamper-proof. A privileged database writer can rewrite the
  retained chain and recompute hashes; external anchoring is required for stronger guarantees.
- SQLite is single-node and is not an active-active or multi-region coordination boundary.
- The deterministic generator and lexical retriever are reference baselines, not evidence of
  real-world language or retrieval quality.

## Portfolio boundary

ResolveOps owns the support-specific business workflow and its resolution transaction. Runtime
authorization, scoped credentials, and action/credential binding may be delegated to AgentGuard
through an executor adapter. ResolveOps must not become a second authorization gateway.

For vulnerability reporting, see [`../SECURITY.md`](../SECURITY.md).
