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

The review transition is atomic at the store boundary. An approved review and its initial
`pending` execution claim are persisted with their audit events in one transaction. This
prevents a crash between approval and execution-intent creation from leaving an approved action
with no recoverable operation.

External side effects cannot share the local database transaction. ResolveOps therefore:

1. persists the execution claim first;
2. derives a stable idempotency key from the approved action;
3. calls the external executor;
4. records `submitted`, `succeeded`, `failed`, or `unknown`;
5. reconciles any non-terminal execution through the adapter;
6. binds every persisted execution transition into audit evidence.

A provider adapter is responsible for implementing reconciliation safely according to the
provider's contract. ResolveOps does not blindly replay an action with a fresh identifier.

Vertical slices are preferred over empty architecture layers. A production action path must
include domain semantics, deterministic policy, an integration contract, failure/retry behavior,
audit evidence, tests, and operator recovery behavior.
