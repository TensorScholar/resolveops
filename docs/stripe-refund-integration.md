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

### First live-execution boundary

The first executable Stripe wedge is deliberately narrower than the read model:

- only USD Charge refunds are executable;
- Stripe Connect charge topologies are fail-closed for execution. Any non-null Connect marker such
  as `application`, `application_fee`, `application_fee_amount`, `on_behalf_of`,
  `source_transfer`, `transfer`, `transfer_data`, or `transfer_group` makes the normalized payment
  non-refundable through this adapter;
- non-USD Charges may still be normalized as billing evidence, but are not live-executable by this
  wedge.

ResolveOps does not currently implement Connect-specific refund semantics such as application-fee
refunds or transfer reversals. Broad currency and Connect support must earn their way in through
separate provider evidence rather than being implied by a generic adapter.

## Submission-time correctness

Approval-time payment snapshot validation remains useful evidence, but it cannot atomically cover a
later remote provider call. The Stripe adapter therefore does **not** add a second local Charge read
and does not claim that repeated observation eliminates the final time-of-check/time-of-use
interval.

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

## Provider error semantics

ResolveOps distinguishes a rejected request from an indeterminate operation:

- `401`/`403` authentication or permission failures are terminal failures for that attempt and are
  not added to reconciliation noise;
- `409`, `424`, `429`, and `5xx` responses preserve uncertainty and must keep the same operation
  identity for retry/reconciliation;
- network failures are also indeterminate; callers retain the same idempotency identity rather than
  inventing a new request;
- deterministic `4xx` request rejections such as an already-refunded Charge are recorded as failed
  immutable requests.

Provider error messages are sanitized before entering ResolveOps state. Request IDs and stable error
codes may be retained for investigation; arbitrary remote diagnostic text is not copied into domain
or audit messages.

## Currency normalization

Stripe's Charge API uses smallest currency units, with documented special cases. ResolveOps keeps
this conversion explicit and tested. For example, JPY uses zero-decimal Charge amounts, while UGX
Charge API amounts retain Stripe's backwards-compatible two-decimal representation. Correct
normalization does not imply that the currency is live-executable: the first refund wedge remains
USD-only.

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

## Authenticated Stripe webhook ingress

ResolveOps has a dedicated Stripe-only webhook ingress rather than adding financial ingress to the
broader reference support API. The application verifies the exact raw request body before parsing
JSON:

1. parse Stripe's `t=` timestamp and one or more `v1=` signatures from `Stripe-Signature`;
2. compute HMAC-SHA256 over `timestamp + "." + raw_body` using the explicitly injected endpoint
   secret and compare signatures in constant time;
3. reject signatures outside the bounded timestamp tolerance;
4. require the event's `livemode` flag to match the configured deployment mode;
5. accept only `refund.created`, `refund.updated`, and `refund.failed` as outcome triggers;
6. require the embedded refund ID to map to exactly one persisted ResolveOps execution;
7. **do not trust the webhook's embedded refund status**. The signed event only triggers an exact
   provider-current refund read through `ActionOutcomeVerifier`;
8. append the resulting outcome observation to the audit chain only after atomically claiming the
   Stripe event identity.

This design intentionally separates authenticity from truth. A valid signature proves Stripe signed
the delivered bytes; it does not prove that an older payload is still the provider's current refund
state. Exact provider retrieval supplies the current observation.

### Webhook replay and concurrency

`MemoryStore` mirrors event claims under its process lock. Persistent webhook deployments use
`SQLiteWebhookStore`, which adds a unique `external_event_claims` record and writes that claim plus
the `action.outcome_observed` event inside one serialized SQLite transaction. Concurrent or retried
delivery of the same Stripe event may repeat the read-only provider lookup, but at most one outcome
observation is committed.

A valid refund event can arrive before the corresponding local execution has learned/persisted its
Stripe refund ID. The dedicated HTTP ingress returns `503` for that race so Stripe can retry rather
than silently losing the trigger. Integrity conflicts return a generic `409`; invalid signatures or
protocol violations return a generic `400`. Internal exception details are not reflected to the
provider.

The ingress currently bounds the accepted signature header and request body in application code.
Production infrastructure must also enforce request-size and rate limits before the ASGI process;
the application-level body limit does not prevent the server from receiving a large body first.

### Webhook secret rotation boundary

The signature parser accepts multiple `v1` values in one Stripe signature header and succeeds when
any value matches the configured endpoint secret. The application currently accepts **one configured
endpoint secret**, however; overlapping rotation between distinct old/new endpoint secrets is not
yet modeled as a first-class deployment capability.

## What deterministic CI proves

The repository's HTTP and application contract tests can prove ResolveOps behavior for:

- exact Charge lookup and identity rejection;
- captured/refunded amount normalization, including Stripe currency special cases;
- USD-only live-execution scope and fail-closed Stripe Connect detection;
- dispute/refundability mapping;
- explicit configuration validation and HTTPS-only provider base URLs;
- exact refund request body and idempotency header;
- authentication/permission versus recoverable/indeterminate provider error classification;
- sanitized provider failures without arbitrary remote error-message persistence;
- provider-current request rejection handling;
- timeout after a simulated provider side effect followed by same-body/same-key recovery;
- refusal to replay an ambiguous old request outside the safe idempotency window;
- exact known-refund reconciliation by GET;
- explicit execution/outcome status mappings, including unknown future provider states;
- a later provider outcome observation changing after execution was already successful;
- raw-body webhook signature verification and bounded replay timestamp checks;
- multiple `v1` signature handling, test/live event separation, and unsupported-event filtering;
- exact webhook refund-to-execution binding without trusting webhook status;
- duplicate and concurrent Stripe event delivery committing at most one outcome observation;
- dedicated webhook HTTP failure mapping and response-detail sanitization.

These tests use in-process HTTP transports and synthetic signed webhook payloads. They prove our
contract logic, not Stripe's live behavior.

## External evidence still required

Live/stable financial readiness remains **NO-GO** until Stripe test mode provides retained evidence
for at least:

1. exact non-Connect USD Charge read and ownership mapping using the pinned API version;
2. successful partial refund;
3. over-refund / already-refunded current-state rejection;
4. ambiguous-response recovery with the same idempotency key and no duplicate refund;
5. `pending` / `requires_action` / `failed` lifecycle handling where test fixtures permit it;
6. refund retrieval after submission and post-action observation;
7. actual Stripe webhook delivery, retry behavior, signature verification, event-to-refund binding,
   duplicate delivery handling, and provider-current outcome refresh through the dedicated ingress.

The connected Stripe session available during development is test mode, but it currently has no
Charge fixture and the connector surface available to this session does not expose the operation
needed to create a PaymentIntent/Charge fixture. That is an external evidence/setup blocker, not a
reason to replace provider evidence with additional mocks.

Deployment identity, authorization, endpoint-secret rotation, infrastructure rate limiting,
network policy, tenant isolation, and optional AgentGuard runtime authorization remain separate
production gates.
