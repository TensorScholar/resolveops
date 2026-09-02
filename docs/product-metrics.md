# Product metrics

ResolveOps measures support outcomes and action integrity, not message volume.

Core product metrics:

- resolution success after action;
- escalation rate;
- human-review rate;
- unresolved-after-action rate;
- external action definitive failure rate;
- external action unknown/ambiguous rate;
- executions requiring reconciliation;
- reconciliation lag;
- stale-evidence rejection count;
- repeat-contact proxy;
- time to resolution;
- cost per successful resolution.

The reference implementation currently exposes only the subset it can define from retained
local data: resolution rate, review rate, evidence coverage, terminal action success/failure
rates, unknown-action rate, actions requiring reconciliation, and cost per resolved outcome.

A metric is not an improvement claim without a baseline. Synthetic fixtures must be labeled
synthetic; self-authored evaluations are not independent product validation.
