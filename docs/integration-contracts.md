# Integration contracts

## Support-case ingestion

An upstream support system supplies a `Ticket` whose `id` is treated as the immutable identity of
one support-case payload for the current ResolveOps transaction model.

The ingestion contract is deliberately strict:

- an exact replay of the same `Ticket.id` and serialized ticket content is idempotent and returns
  the existing canonical analysis;
- that replay is retrieval of the already-created resolution transaction; it does not regenerate
  the analysis from mutable customer-profile or billing state;
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

## Billing reader and refund target binding

A refund-capable upstream integration supplies an explicit `Ticket.payment_reference`. ResolveOps
does **not** search a customer's payments, select a latest charge, or infer a financial resource
from amount/date similarity.

`BillingReader.get_payment(payment_id)` is deliberately the only billing lookup contract in this
slice. It returns a normalized `PaymentSnapshot` containing the exact payment identity, owner,
original amount, already-refunded amount, currency, refundability, and provider status. A reader
must return either the payment whose `id` exactly equals the requested `payment_id` or `None`;
returning a different payment is an integrity violation and ResolveOps fails the ingestion before
persisting an analysis.

All safety-relevant `PaymentSnapshot` state is explicit. `amount_refunded`, `refundable`, and
`status` are required fields rather than optimistic defaults, so an incomplete adapter mapping is
rejected by schema/model validation instead of being treated as an unrefunded, refundable,
succeeded payment.

Before a refund action can be proposed, ResolveOps verifies:

- the explicit payment exists;
- the returned payment identity exactly matches the explicit payment reference;
- the payment belongs to the ticket customer;
- the payment is still refundable and has a positive remaining refundable amount;
- an explicitly stated refund currency matches the payment currency;
- the requested amount, when known, does not exceed the remaining refundable amount.

Refund amount extraction is deliberately conservative. An unmarked number is not money, and if
customer text contains multiple distinct explicit USD amounts, ResolveOps does not guess which one
is the refund amount. The proposal remains non-executable until an unambiguous amount is supplied.
Repeated occurrences of the same explicit amount remain unambiguous.

A valid refund `ActionProposal` is then bound to:

- `resource_kind=payment`;
- the exact payment ID as `resource_id`;
- a digest of the complete normalized payment snapshot as `resource_hash`;
- the normalized payment currency;
- the requested amount, when explicitly known.

At approval time, ResolveOps reads the same payment ID again. The returned identity and ownership
must still match, and the current normalized snapshot digest must equal the digest reviewed during
analysis. If the reader substitutes another identity, or the payment disappears or changes,
approval fails closed before execution persistence.

This approval-time check reduces stale-target risk but cannot eliminate the final race between the
last read and the external side effect. A production billing/refund adapter must still enforce its
provider's current refund constraints when it submits the operation.

The in-memory billing reader is a deterministic reference adapter for tests and local demos. It is
not evidence of a live billing integration.

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

A refund executor must reject an action that is not structurally bound to a verified payment
resource. The application and policy layer enforce the same invariant before an execution claim
can cross the provider boundary.

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

For refunds, reconciliation intentionally does **not** require the current payment snapshot to
match the pre-side-effect `resource_hash`: the refund itself may have changed `amount_refunded`,
status, or other provider state. Recovery instead preserves the already-approved payment ID,
action parameters, internal idempotency identity, and any known external operation reference.

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
