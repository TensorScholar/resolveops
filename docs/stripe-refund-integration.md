# Stripe refund integration

This integration is intentionally one narrow support-resolution transaction: an explicit Stripe
Charge is read as billing evidence, one approved refund is submitted against that Charge, and the
result is reconciled and observed over time. It is not a generic Stripe connector layer.

## Canonical resource

`Ticket.payment_reference` is a Stripe Charge ID (`ch_...`). ResolveOps never lists a customer's
charges, chooses a latest payment, or matches a charge by amount/date heuristics.

`StripeRefundGateway.get_payment(charge_id)` performs one exact Charge lookup and normalizes:

- the exact Charge ID;
- Stripe Customer ID;
- captured amount (not merely intended amount);
- amount already refunded;
- currency;
- captured/paid/disputed/status state into the `refundable` decision.

A missing customer identity or malformed/mismatched provider object is an integration contract
failure, not a reason to manufacture optimistic financial state.

## Submission-time correctness

Approval-time payment snapshot validation remains useful evidence, but it cannot atomically cover a
later remote provider call. The Stripe adapter therefore does **not** claim that a second local read
eliminates the final time-of-check/time-of-use interval.

The actual refund POST targets the exact approved Charge and amount. Stripe's Refunds API enforces
its current remaining-refundable constraint when the refund request executes: an entirely refunded
Charge or a request larger than the remaining amount is rejected by Stripe. This provider-side
constraint is the financial submission boundary for this adapter.

The adapter sends:

- `charge=<approved ch_...>`;
- exact amount in the Charge currency's smallest unit;
- `reason=requested_by_customer`;
- non-sensitive ResolveOps analysis/approval identifiers and an idempotency-key digest in metadata;
- the stable ResolveOps execution key in the `Idempotency-Key` header.

The Stripe secret key is constructor-injected into the HTTP client only. It is not stored in domain
objects, audit events, action metadata, or idempotency keys. The Stripe API version is also an
explicit constructor argument so a production integration cannot silently depend on whichever API
version an account happens to use.

## Ambiguous-response recovery

If a Stripe refund ID is already known, reconciliation performs an exact `GET /v1/refunds/{id}` and
does not create a new operation.

If the provider may have accepted a refund but the response was lost before ResolveOps learned the
refund ID, reconciliation can repeat the **exact same POST body with the exact same idempotency
key** only inside a conservative replay window shorter than 24 hours.

Stripe documents that idempotency results are replayed for the same key, including `500` results,
but that keys may be pruned after they are at least 24 hours old. Reusing a pruned key can create a
new request. ResolveOps therefore defaults to a 23-hour maximum replay window and refuses blind POST
replay after that boundary. An old ambiguous operation requires provider/manual investigation.

## Execution success is not a verified customer outcome

`ActionExecution` records the command transaction. Stripe can currently return a refund with
`succeeded`, so that command can reach ResolveOps `ExecutionState.SUCCEEDED`.

That does **not** mean the customer outcome is permanent. Stripe documents refund states including
`pending`, `requires_action`, `succeeded`, `failed`, and `canceled`; some failures can occur much
later, and some payment methods can return funds to Stripe after an earlier `succeeded` state.

ResolveOps therefore stores post-action verification as append-only `ActionOutcomeObservation`
events in the existing tamper-evident audit chain. A later observation can supersede the current
operational interpretation of an earlier observation without rewriting the original execution or
its history.

The current state mapping is:

| Stripe refund status | Command execution | Outcome observation |
| --- | --- | --- |
| `pending` | `submitted` | `pending` |
| `requires_action` | `submitted` | `requires_action` |
| `succeeded` | `succeeded` | `verified` |
| `failed` / `canceled` | `failed` | `failed` |
| unknown status | `unknown` | `unknown` |

`verified` means **the provider currently verifies the successful outcome**. It is an observation,
not an immutable terminal truth. Later observations remain append-only and may report a different
state.

## What deterministic CI proves

The repository's HTTP contract tests can prove ResolveOps behavior for:

- exact Charge lookup and identity rejection;
- captured/refunded amount normalization, including zero-decimal currencies;
- dispute/refundability mapping;
- exact refund request body and idempotency header;
- provider-current request rejection handling;
- timeout after a simulated provider side effect followed by same-body/same-key recovery;
- refusal to replay an ambiguous old request outside the safe idempotency window;
- exact known-refund reconciliation by GET;
- a later provider outcome observation changing after execution was already successful.

These tests use an in-process HTTP transport. They prove our contract logic, not Stripe's live
behavior.

## External evidence still required

Live/stable financial readiness remains **NO-GO** until Stripe test mode provides retained evidence
for at least:

1. exact Charge read and ownership mapping using the pinned API version;
2. successful partial refund;
3. over-refund / already-refunded current-state rejection;
4. ambiguous-response recovery with the same idempotency key and no duplicate refund;
5. `pending` / `requires_action` / `failed` lifecycle handling where test fixtures permit it;
6. refund retrieval after submission and post-action observation;
7. webhook signature verification and replay handling before webhooks become an enabled production
   ingestion path.

The current reference FastAPI application remains unauthenticated and therefore does not wire live
Stripe destructive execution. Deployment identity, authorization, secret rotation, tenant
isolation, and optional AgentGuard runtime authorization remain separate production gates.
