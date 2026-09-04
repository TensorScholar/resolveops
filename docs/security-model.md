# Security model

ResolveOps protects a narrow support-operations integrity boundary: untrusted customer text and
generated content may propose a high-impact action, but deterministic policy, evidence checks,
verified resource binding, review state, durable execution intent, reconciliation, and authenticated
provider-outcome ingestion constrain whether the action can become or remain an external side
effect.

## Protected assets

- customer and support-case context;
- approved knowledge and its provenance;
- normalized billing/payment snapshots used to support refund decisions;
- analysis and policy decisions;
- action proposals and human approvals;
- execution identity, idempotency key, provider state, and reconciliation history;
- authenticated external-event identity and post-action outcome observations;
- recorded support outcomes;
- audit evidence.

## Primary threats

1. **Instruction or prompt injection** — ticket text attempts to override policy or execution.
2. **Unsupported or stale evidence** — missing, revoked, expired, replaced, future-dated, or
   changed knowledge supports an unsafe action.
3. **Ambiguous action parameters** — an amount, target, or destructive operation is inferred
   without sufficient support.
4. **Wrong financial target** — a refund is attached to a customer or heuristically selected
   payment rather than one explicit system-of-record payment.
5. **Stale payment state** — ownership, refunded amount, refundability, currency, or provider state
   changes after analysis but before approval.
6. **Case-ingestion replay or identity collision** — the same support case is analyzed more than
   once into distinct resolution transactions, or one case ID is reused for changed content.
7. **Canonical-record mutation** — a lower-level persistence helper rewrites a ticket or analysis
   after canonical ownership has been established.
8. **Approval replay** — an analysis is approved or rejected more than once.
9. **Lost execution intent** — a process crashes after approval but before the operation is
   durably represented.
10. **Duplicate external side effect** — a retry creates a second refund/change/cancellation.
11. **Ambiguous provider outcome** — the provider accepts the action but the response is lost.
12. **Stale non-terminal state** — an accepted provider operation later fails or requires action
    without ResolveOps reconciling it.
13. **Forged, replayed, or colliding webhook** — an attacker fabricates provider events, replays a
    valid event, reuses an event identity for different semantics, crosses test/live boundaries, or
    exploits concurrent delivery to create duplicate outcome facts.
14. **Stale or out-of-order webhook payload** — a signed provider event contains an older status
    than the provider's current operation state and is mistaken for authoritative truth.
15. **Persistence or concurrency faults** — stored models are malformed, attempts race, or audit
    sequence allocation collides.
16. **Audit mutation** — retained events are edited, reordered, or truncated.
17. **Sensitive-data leakage** — logs, fixtures, keys, or repository content expose secrets or
    customer information.
18. **Boundary confusion** — ResolveOps is treated as a credential gateway, billing ledger, or
    horizontally scalable coordination service.

## Current controls

- deterministic business policy is isolated from generated response content;
- retrieval accepts only approved, temporally valid knowledge and binds article content digests;
- action parameters required by policy fail closed when ambiguous;
- destructive actions remain human-gated;
- refund triage cannot create a customer-targeted refund action from text alone;
- refund ingestion requires an explicit upstream payment reference; the billing port exposes only
  exact `get_payment(id)` lookup and no customer/latest-payment discovery API;
- payment ownership, refundability, normalized currency, and remaining refundable amount are
  checked before a refund proposal is created;
- a valid refund proposal binds the exact payment ID and normalized payment snapshot digest;
- approval re-reads the same payment and rejects disappearance, ownership change, or any snapshot
  digest change before an execution claim is persisted;
- the first Stripe execution wedge is deliberately limited to non-Connect USD Charge refunds;
  broader currency and Connect semantics fail closed until separately evidenced;
- the Stripe adapter receives its secret and API version explicitly, keeps credentials out of
  domain/audit state, sends the stable ResolveOps idempotency key, and preserves exact request
  identity across ambiguous-response reconciliation;
- known Stripe refund IDs reconcile through exact refund retrieval, while blind POST replay is
  refused after the conservative provider-idempotency replay window;
- unverified legacy refund actions remain decodable for migration/forensics but are non-executable
  in policy, application execution, and the reference executor;
- one exact `Ticket.id` + ticket-content digest is bound to one canonical analysis at the store
  boundary;
- ticket, canonical analysis claim, analysis object, and `ticket.analyzed` audit evidence are
  committed atomically on application ingestion;
- identical case replays converge on the canonical analysis, while reuse of a ticket ID with
  changed content—including a changed payment reference—fails closed;
- low-level ticket/analysis helper writes cannot mutate objects after a canonical analysis claim
  owns them;
- analysis-claim backfill requires audit evidence that binds both the exact ticket digest and
  exact analysis digest; older audit history without ticket-payload binding is rejected rather
  than inferred;
- ambiguous legacy history containing multiple analyses for one ticket is rejected instead of
  guessing which resolution transaction should become canonical;
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
- refund reconciliation preserves the approved payment/action identity but intentionally does not
  demand equality with the pre-side-effect payment snapshot, because the side effect itself may
  have changed payment state;
- post-action outcome observations are append-only and preserve the original command execution
  history rather than rewriting a previously successful execution;
- Stripe webhook HMAC is verified against the exact raw request body before JSON parsing, using
  the signed timestamp plus a bounded tolerance and constant-time signature comparison;
- the webhook verifier can receive an explicit set of active endpoint secrets, allowing old/new
  Stripe rotation overlap without disabling signature verification or weakening timestamp checks;
- webhook `livemode` must match the deployment's configured mode, preventing test/live event
  crossing;
- only `refund.created`, `refund.updated`, and `refund.failed` are accepted as Stripe refund
  outcome triggers; unrelated signed events are acknowledged without provider reads;
- the signed webhook payload is not treated as outcome truth: its refund ID must bind to exactly
  one persisted execution, then ResolveOps performs an exact current provider read through the
  outcome verifier;
- a provider-current read failure during webhook processing does not claim the event or append an
  UNKNOWN fact; the dedicated ingress returns retryable `503` so a later delivery can retry the
  exact read. Manual outcome observation remains a separate path that may record `unknown`;
- Stripe event IDs are bound to an immutable event-identity digest covering mode, event ID, event
  type, and refund ID. Sequential conflicting reuse fails closed, and `SQLiteWebhookStore` verifies
  that identity inside the serialized claim transaction;
- Stripe event IDs are claimed atomically with the outcome audit append. MemoryStore mirrors the
  normal duplicate semantics under a lock, while `SQLiteWebhookStore` uses `BEGIN IMMEDIATE` plus a
  unique external-event claim so concurrent/retried delivery can commit at most one outcome fact;
- the dedicated Stripe webhook FastAPI surface contains only health and webhook routes, bounds the
  accepted signature header and body size, returns retryable `503` when processing is temporarily
  unavailable, and does not leak internal exception text;
- SQLite audit allocation and ingestion/review/execution transitions use serialized
  transactions;
- malformed or internally inconsistent persisted models fail closed as integrity errors;
- repository secret/static-security checks run in CI;
- the domain has no vendor SDK, network client, FastAPI, or SQLite dependency.

## Residual risks

These controls do not make ResolveOps a production authorization or financial system.

- Case-level canonicalization uses immutable `Ticket.id` plus exact content; mutable upstream
  cases need an explicit revision/event identity contract rather than silent in-place reuse of
  the same ID.
- Exact replay returns the historical canonical resolution transaction and intentionally does not
  re-run mutable customer-profile or billing-state analysis. Billing state is revalidated at
  approval; authentication, authorization, and upstream revision semantics remain integration
  responsibilities.
- The approval-time payment read cannot eliminate the final time-of-check/time-of-use race before
  an external provider call. Stripe's current-state request rejection is the financial submission
  boundary for the current adapter; real test-mode evidence is still required.
- The deterministic Stripe adapter has not yet been validated against a retained real Charge/refund
  fixture in the connected Stripe test account. Provider-side idempotency, lifecycle, current-state
  rejection, and delivery behavior therefore remain external evidence gates.
- Concurrent duplicate ingestion can still repeat pre-persistence analysis computation before
  the serialized store transaction selects the canonical analysis; this wastes compute but does
  not create a second persisted resolution transaction.
- Persisting `in_flight` before a provider call is conservative: a process can terminate after
  the local transition but before the request reaches the provider. ResolveOps therefore knows
  that an attempt may have started, not that the provider necessarily observed it.
- A provider operation can remain non-terminal (`in_flight`, `submitted`, or `unknown`) for an
  extended period. Production integrations need an operator policy for stale state even when
  webhook/reconciliation triggers exist.
- Application support for overlapping endpoint-secret rotation does not manage secret storage,
  distribution, retirement timing, or deployment orchestration; those remain deployment controls.
- Request-body limiting occurs after the ASGI server has received the body. Production ingress
  still needs infrastructure-level request-size enforcement, rate limiting/WAF controls, network
  policy, deployment identity, authorization, and tenant routing.
- Deterministic tests prove HMAC/replay/concurrency behavior but do not prove Stripe's real retry,
  event-ordering, or refund-event delivery behavior; retained test-mode webhook evidence remains
  required.
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
