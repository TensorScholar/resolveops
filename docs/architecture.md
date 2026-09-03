# Architecture

ResolveOps is a modular monolith. Its primary aggregate is a **support-resolution transaction**:
evidence and policy produce an explicit action proposal; financial actions can additionally bind
to a verified system-of-record resource; review creates a durable execution intent; provider
interaction advances that execution through reconciliation to a terminal outcome.

```text
CLI / FastAPI / composition root
          |
   application service
     /          \
 domain       billing reader
models/policy   (read-only)
     |
    ports
  /      \
store     response generator
          action executor
```

Dependency rules:

- `domain` imports only the standard library, Pydantic schema types, and sibling domain modules;
- `application` imports domain and ports, never adapters;
- `ports` import domain types;
- `adapters` implement ports;
- the composition root selects adapters for web, CLI, and demos;
- vendor SDKs and network clients never enter the domain layer;
- billing discovery is not a domain capability: the current port accepts only an explicit
  payment identity and returns a normalized snapshot.

## Transaction boundaries

### Case ingestion

Application ingestion uses the store-level `record_analysis` transition rather than separately
persisting a ticket, analysis, and audit event. The transition binds one `Ticket.id` to:

- the digest of the exact persisted ticket payload;
- one canonical `AnalysisResult`;
- one `ticket.analyzed` audit event.

SQLite stores this relationship in `analysis_claims` and commits the ticket, analysis, claim, and
audit event under one `BEGIN IMMEDIATE` transaction. An identical replay returns the canonical
analysis. Reusing the same ticket ID with different content fails closed. Concurrent duplicate
requests may perform redundant analysis work before persistence, but only one canonical analysis
can commit and all successful callers converge on that persisted result.

Concrete adapter helper writes are not part of the application `Store` contract. They are also
prevented from mutating a ticket or analysis once that ticket owns a canonical analysis claim, so
low-level fixture/setup access cannot silently invalidate canonical ownership after ingestion.

On startup, a database missing an analysis claim can receive one only when hash-chained
`ticket.analyzed` evidence already binds both the exact persisted ticket digest and the exact
analysis digest. Historical events that predate ticket-payload binding are rejected rather than
guessed into the new canonical model. Multiple historical analyses for one ticket are likewise
rejected because no safe canonical choice can be inferred.

An exact replay is retrieval of the already-created resolution transaction. It therefore does
not regenerate the analysis from mutable customer-profile or billing state. Mutable upstream case
revisions, identity/authorization checks, and new resolution decisions require explicit
integration contracts rather than changing the semantics of an idempotent replay.

### Refund payment binding

Refund targeting is resolved before policy can create an executable proposal. The upstream ticket
must carry an explicit payment reference. The application then performs an exact
`BillingReader.get_payment(id)` read and normalizes the result into `PaymentSnapshot`.

The application verifies payment ownership, refundability, currency, and remaining refundable
amount. A valid proposal records `resource_kind=payment`, the exact payment ID, normalized
currency, and a digest of the entire payment snapshot. There is intentionally no
`list_payments(customer)` or "latest payment" port because that would reintroduce financial-target
ambiguity into the architecture.

Case ingestion persists the resulting analysis and payment-bound action as part of the same
canonical resolution transaction. The payment snapshot itself remains owned by the external
system of record; ResolveOps stores its digest in the action rather than pretending to become a
billing ledger.

### Review and execution

Before approving a refund, the application re-reads the exact payment. The owner must still match
and the normalized snapshot digest must equal the digest captured during analysis. A missing or
changed payment fails closed before approval/execution persistence and requires a new analysis.

This read cannot be part of the same atomic transaction as the external billing system. There is
therefore still a final time-of-check/time-of-use interval between approval-time verification and
the provider side effect. The production executor must independently apply the provider's current
constraints at submission time.

The local review transition itself is atomic at the store boundary. An approved review and its
initial `pending` execution claim are persisted with their audit events in one transaction. This
prevents a crash between approval and execution-intent creation from leaving an approved action
with no recoverable operation.

External side effects cannot share the local database transaction. ResolveOps therefore:

1. persists the execution claim and stable idempotency key;
2. persists an `in_flight` transition and increments the attempt number **before** invoking the
   external adapter;
3. calls the external executor;
4. completes that same attempt as `submitted`, `succeeded`, `failed`, or `unknown` without
   incrementing it again;
5. if the process terminates after step 2, retains an auditable `in_flight` execution instead of
   pretending no attempt occurred;
6. reconciles any non-terminal execution through the adapter, again persisting a new
   `in_flight` attempt before crossing the provider boundary;
7. binds every persisted execution transition into audit evidence.

Persisting `in_flight` before the call is intentionally conservative: a process can terminate
after the local transition but before bytes reach the provider. ResolveOps therefore treats an
orphaned `in_flight` state as uncertain and reconciles it using the same action identity rather
than assuming either success or non-execution.

For a refund, reconciliation preserves the approved payment ID, action parameters, idempotency
identity, and any known external operation reference. It does not require the current billing
snapshot to equal the pre-side-effect digest, because the original side effect may itself have
changed refunded amount or provider status.

A provider adapter is responsible for implementing reconciliation safely according to the
provider's contract. ResolveOps does not blindly replay an action with a fresh identifier.

Vertical slices are preferred over empty architecture layers. A production action path must
include domain semantics, deterministic policy, an integration contract, failure/retry behavior,
audit evidence, tests, and operator recovery behavior.
