# Architecture

ResolveOps is a modular monolith. Its primary aggregate is a **support-resolution transaction**:
evidence and policy produce an explicit action proposal; review creates a durable execution
intent; provider interaction advances that execution through reconciliation to a terminal
outcome.

```text
CLI / FastAPI / composition root
          |
   application service
          |
   domain models + policy
          |
        ports
      /       \
 SQLite       response generator
 memory       action executor
```

Dependency rules:

- `domain` imports only the standard library, Pydantic schema types, and sibling domain modules;
- `application` imports domain and ports, never adapters;
- `ports` import domain types;
- `adapters` implement ports;
- the composition root selects adapters for web, CLI, and demos;
- vendor SDKs and network clients never enter the domain layer.

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
not regenerate the analysis from mutable customer-profile state. Mutable upstream case revisions,
identity/authorization checks, and new resolution decisions require explicit integration
contracts rather than changing the semantics of an idempotent replay.

### Review and execution

The review transition is atomic at the store boundary. An approved review and its initial
`pending` execution claim are persisted with their audit events in one transaction. This
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

A provider adapter is responsible for implementing reconciliation safely according to the
provider's contract. ResolveOps does not blindly replay an action with a fresh identifier.

Vertical slices are preferred over empty architecture layers. A production action path must
include domain semantics, deterministic policy, an integration contract, failure/retry behavior,
audit evidence, tests, and operator recovery behavior.
