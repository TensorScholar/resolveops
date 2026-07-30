# Implementation risk register

| Risk | Failure mode | Practical mitigation | Evidence required |
|---|---|---|---|
| Unsupported answer | Agent invents policy | Evidence threshold and escalation; generator cannot execute actions | labeled citation fixture |
| Prompt injection | Ticket text asks system to ignore policy | Policy is deterministic and outside generator output | adversarial ticket tests |
| Stale policy | Old article supports unsafe reply | article approval, expiry, and maximum-age checks | stale-source tests |
| Action ambiguity | Refund amount or target is missing | require review; never infer money silently | unknown-amount test |
| Excessive refund | Proposal exceeds business ceiling | deterministic deny before review | boundary tests |
| Approval misuse | Rejected or irrelevant review executes | explicit immutable transition and action binding | replay/transition tests |
| Tool failure | External API times out after approval | fail closed, record unknown/failure, no blind retry | adapter contract tests |
| Audit mutation | Event is edited or reordered | hash chain plus external-head recommendation | tamper tests |
| PII leakage | Logs include raw customer data | structured allowlisted audit payloads and redaction adapter | secret/PII scan |
| Concurrency | Duplicate approval or execution | database uniqueness and idempotency key in production adapter | concurrent tests |
| Metric gaming | High automation but poor outcomes | optimize resolution, CSAT, unsafe-action rate, and cost per outcome | pilot scorecard |
| SQLite boundary | Multiple replicas diverge | declare single-node; migrate coordination to Postgres before scale-out | deployment review |
| Vendor lock-in | LLM SDK spreads through domain | ResponseGenerator port; offline baseline | architecture check |
| Over-engineering | Product becomes an agent platform | one workflow, three actions, no control plane | roadmap review |
