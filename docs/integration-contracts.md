# Integration contracts

## Support-case ingestion

An upstream support system supplies a `Ticket` whose `id` is treated as the immutable identity of
one support-case payload for the current ResolveOps transaction model.

The ingestion contract is deliberately strict:

- an exact replay of the same `Ticket.id` and serialized ticket content is idempotent and returns
  the existing canonical analysis;
- that replay is retrieval of the already-created resolution transaction; it does not regenerate
  the analysis from mutable customer-profile state;
- the same `Ticket.id` with different content is an integrity conflict and is rejected rather
  than silently treated as a revision;
- an integration whose source cases are mutable must provide a distinct immutable event/version
  identity, or define a future explicit revision contract before those updates are ingested;
- connector retries must preserve the source ticket identity rather than minting a new ID for
  the same logical delivery;
- authentication, authorization, and mutable upstream customer/case validation remain integration
  responsibilities and must not be implemented by changing canonical replay semantics.

Concrete store helpers used by tests or local setup are outside the application `Store` port and
cannot rewrite a ticket or analysis after canonical ownership has been established.

A database without an analysis claim is upgraded only when existing hash-chained audit evidence
already binds both the exact ticket payload digest and exact analysis digest. Older audit history
without `ticket_hash` is intentionally rejected because ResolveOps cannot prove which historical
payload produced the analysis.

This is case-level canonicalization inside ResolveOps. It is not generic cross-system entity
matching and does not establish idempotency for a later external refund/change/cancellation.

## Response generator

A response provider receives a ticket, customer context, evidence, and normalized intent. It
returns a summary, draft reply, and confidence. It cannot directly execute tools or change
business policy.

## Action executor

An action executor receives:

- the explicit `ActionProposal`;
- the approved `Approval`;
- a stable, non-sensitive idempotency key.

Before either `execute` or `reconcile` is invoked, ResolveOps persists the execution as
`in_flight` and increments its attempt number. This transition occurs before the provider
boundary so process termination cannot erase the fact that an adapter interaction may have
started. A returned provider result completes that same attempt; it does not increment the
attempt number again.

The executor returns an `ExecutionResult` with an external lifecycle state, a sanitized message,
an optional opaque external reference, and an optional provider status. `pending` and
`in_flight` are internal ResolveOps states and are not valid executor results.

The executor must not translate transport uncertainty into a definitive failure. If the caller
cannot establish the provider outcome, the result is `unknown`.

## Reconciliation

`ActionExecutor.reconcile(execution)` is a separate contract for non-terminal executions.
Implementations must be side-effect-safe. Depending on the provider, reconciliation can use a
read API, webhook-derived state, or a retry with the **same** provider-supported idempotency key.

Reconciliation must never invent a fresh action identity merely because the original response
was lost. A known external operation reference is immutable once recorded; later reconciliation
must continue to refer to that operation.

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
