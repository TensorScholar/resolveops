# Documentation

ResolveOps keeps the repository root intentionally small. Detailed design, safety, validation, and release material lives here.

## Core design

- [Architecture](architecture.md) — dependency boundaries and composition model.
- [Architecture decision records](adr/) — decisions that materially shape the design.
- [Integration contracts](integration-contracts.md) — external-facing ports and integration expectations.
- [Product metrics](product-metrics.md) — outcome-oriented measurements used by the reference workflow.

## Safety and operating boundaries

- [Security model](security-model.md) — protected assets, threats, controls, implementation risks, and residual risks.
- [Limitations](limitations.md) — capabilities intentionally outside the current release candidate.

## Release and project direction

- [Release validation](release-validation.md) — reproduced defects, remediation, final CI evidence, and residual limitations for `0.1.0rc2`.
- [Release process](releasing.md) — release checklist and publication requirements.
- [Roadmap](roadmap.md) — narrowly scoped next steps after external review.

Repository-level contribution, security-reporting, changelog, license, and citation files remain at the project root because GitHub and packaging tooling expect them there.