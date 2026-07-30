# Integration contracts

## Response generator

A provider receives a ticket, customer context, evidence, and normalized intent. It returns
a summary, draft reply, and confidence. It cannot directly execute tools or change policy.

## Action executor

An executor receives an explicit action proposal and an approved review object. It returns
success, a sanitized message, and an opaque external reference.

## AgentGuard

A production integration may place AgentGuard between approval and action execution.
ResolveOps intentionally defines the business workflow and leaves runtime authorization to
a dedicated adapter.
