# Integration contracts

## Response generator

A response provider receives a ticket, customer context, evidence, and normalized intent. It
returns a summary, draft reply, and confidence. It cannot directly execute tools or change
business policy.

## Action executor

An action executor receives:

- the explicit `ActionProposal`;
- the approved `Approval`;
- a stable, non-sensitive idempotency key.

It returns an `ExecutionResult` with an explicit lifecycle state, a sanitized message, an
optional opaque external reference, and an optional provider status.

The executor must not translate transport uncertainty into a definitive failure. If the caller
cannot establish the provider outcome, the result is `unknown`.

## Reconciliation

`ActionExecutor.reconcile(execution)` is a separate contract for non-terminal executions.
Implementations must be side-effect-safe. Depending on the provider, reconciliation can use a
read API, webhook-derived state, or a retry with the **same** provider-supported idempotency key.

Reconciliation must never invent a fresh action identity merely because the original response
was lost.

Provider-specific adapters are also responsible for documenting:

- which external resource the action targets;
- timeout and retry semantics;
- idempotency retention/limits;
- provider terminal and non-terminal states;
- webhook/event authenticity when used;
- how ambiguous responses are resolved;
- what external reference proves the operation.

## AgentGuard boundary

A production executor may place AgentGuard between approval and the external side effect.
ResolveOps owns support-specific evidence, policy, review, transaction state, reconciliation,
and outcome measurement. AgentGuard may own runtime authorization, credential/action binding,
and execution-integrity enforcement. ResolveOps does not reimplement those responsibilities.
