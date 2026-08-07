# Release validation — ResolveOps 0.1.0rc2

This document records the evidence boundary for the `0.1.0rc2` engineering release candidate. It replaces the earlier transfer-oriented audit/status documents with a single current validation record.

## Release status

**Decision:** suitable as an inspectable engineering release candidate for demonstration and external review.

**Production deployment:** not claimed. Live production use still requires identity, authorization, tenant isolation, secret management, provider idempotency/reconciliation, operational controls, and stronger audit anchoring.

## Canonical validation baseline

The application implementation integrated into GitHub `main` was validated at commit:

`57b1395d5f8da53f15d57616e814665d3b670b33`

with tree:

`6821391f5aca9d5819babfbfa3dfbaae8de9c7e4`

The final native GitHub `push` CI run for that baseline completed successfully across Python 3.11, 3.12, and 3.13.

### CI gates

Each supported Python job passed:

- packaging-toolchain bootstrap;
- editable installation with development and web extras;
- Ruff format check;
- Ruff lint;
- strict MyPy;
- architecture dependency validation;
- repository secret scanning;
- local static-security scanning;
- generated-schema consistency;
- the full pytest suite with `ResourceWarning` promoted to an error;
- branch-aware coverage enforcement;
- the offline end-to-end demo;
- dependency vulnerability auditing with `pip-audit`.

The validated suite contains **72 tests** and reports **96.11% branch-aware coverage**, above the required 85% threshold.

## Additional reproduced release checks

The release process also reproduced:

- source and wheel builds;
- Twine metadata validation;
- package installation smoke testing;
- release metadata consistency;
- JSON schema generation consistency;
- Git object integrity with `git fsck --full --strict`;
- clean working-tree and Local/GitHub synchronization checks;
- recovery-bundle integrity and SHA-256 verification.

The Python dependency audit initially exposed a vulnerability in the CI packaging bootstrap (`setuptools 79.0.1`, advisory `PYSEC-2026-3447`). The workflows were corrected to upgrade the packaging toolchain with `setuptools>=83`; the complete Python 3.11–3.13 validation matrix then passed.

## Material defects reproduced and remediated

Independent adversarial validation of the earlier candidate identified integrity and safety defects that were fixed before the canonical release candidate was integrated. Material corrections included:

- policy is re-evaluated immediately before review and fails closed;
- evidence must remain approved, current, non-future, and content-consistent;
- refund amounts and plan targets must be explicit;
- analyses are bound into audit evidence;
- approval/execution replay is blocked;
- SQLite audit sequence allocation is serialized;
- malformed persisted models fail as integrity errors;
- external-executor uncertainty blocks blind replay;
- unsupported automatic destructive actions were removed;
- FastAPI validation/error mapping, architecture checks, secret scanning, and Docker data-path handling were hardened.

## Evidence interpretation

A passing local secret scanner or static-security script demonstrates only that the repository-specific checks passed. It is not equivalent to a comprehensive penetration test or production security assessment.

Likewise, the current CI validates the reference implementation and packaging boundary; it does not validate live CRM, billing, identity, or help-desk integrations because those connectors are intentionally not included.

## Residual limitations

The main residual boundaries are documented in [`security-model.md`](security-model.md) and [`limitations.md`](limitations.md). In particular:

- audit evidence is tamper-evident rather than independently tamper-proof;
- SQLite remains a single-node persistence boundary;
- the bundled executor is a mock integration;
- the API lacks a production identity/authorization/tenant boundary;
- external side effects require provider idempotency and reconciliation;
- no real-customer pilot or production operational validation is claimed.

## Documentation-only maintenance

Repository presentation or documentation-only commits after the baseline above do not change the validated application behavior, but they must still pass the repository CI before merge, especially when release metadata or release-check scripts are updated.