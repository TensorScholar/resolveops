# ResolveOps canonicalization and validation report

**Project:** ResolveOps
**Input release:** `0.1.0rc1` handoff archive
**Canonical release:** `0.1.0rc2`
**Audit date:** 2026-08-06
**Decision:** **READY FOR GITHUB TRANSFER WITH EXPLICIT LIMITATIONS**
**Production readiness:** **NOT CLAIMED**

## 1. Scope and evidence rules

This review treated the ZIP, its internal reports, and all release claims as untrusted until
reproduced. The uploaded ZIP and SHA-256 sidecar were retained unchanged. All remediation
was performed in a separate Git clone.

Status terms:

- **PASS**: directly reproduced in this environment.
- **FAIL**: directly reproduced defect or failed gate.
- **BLOCKED**: execution was attempted but the environment prevented completion.
- **NOT TESTED**: no direct execution evidence exists.
- **UNKNOWN**: the available evidence cannot establish the result.

## 2. Input provenance

| Check | Result | Evidence |
|---|---:|---|
| Uploaded ZIP SHA-256 matches sidecar | PASS | `225266ddf2a6cddfb29ef12db3a0325b84da701ad3e5edcd877bc22e3e836995` |
| ZIP central-directory integrity | PASS | `unzip -t` |
| Unsafe paths, duplicate paths, symlinks, special files, encrypted entries | PASS | independent ZIP metadata scan |
| Suspicious expansion ratio / archive bomb pattern | PASS | 264 entries; 554,210 uncompressed bytes; aggregate ratio 2.03 |
| Internal `HANDOFF_SHA256SUMS` | PASS | all listed files matched |
| Original Git object integrity | PASS | `git fsck --full --strict` |
| Original Git working tree | PASS | clean at `98f8319be5795983566bff7dee96310d02772efa` |
| Original uploaded files modified | PASS (no) | final hashes rechecked during packaging |

## 3. Baseline reproduction

The original candidate passed its own test suite: 51 tests and 97.16% branch-aware
coverage. That result did **not** establish safety. Independent adversarial reproduction
found the following defects. Impact ratings are reviewer assessments, not CVSS scores.

| Impact | Reproduced baseline defect | Baseline result |
|---|---|---:|
| High | Review ignored `action_allowed=False`; refund with unknown amount executed | FAIL |
| High | Missing-evidence analysis could still be approved and executed | FAIL |
| High | Same analysis could be approved and executed repeatedly | FAIL |
| High | Concurrent SQLite audit append lost events through sequence collisions | FAIL |
| High | Persisted action data was not bound to audit evidence | FAIL |
| High | Revoked, expired, replaced, or silently changed evidence was not revalidated at review | FAIL |
| Medium | Future-dated knowledge could be retrieved | FAIL |
| Medium | Unmarked numbers could be parsed as refund amounts | FAIL |
| Medium | Ambiguous plan change defaulted to a target plan | FAIL |
| Medium | Corrupt persisted JSON leaked a raw validation exception | FAIL |
| Medium | SQLite connections produced resource warnings | FAIL |
| Medium | Advertised automatic-action settings had no safe runtime execution path | FAIL |
| Medium | Container used a non-root user but the default database path was not writable | FAIL by inspection |

The raw reproduction is retained in `baseline-logs/adversarial-reproduction.txt`.

## 4. Canonical remediation

The canonical branch makes these material changes:

- re-evaluates policy immediately before review and fails closed;
- requires explicit refund amounts and explicit plan targets;
- requires approved, non-future, non-expired, age-compliant evidence;
- binds the full knowledge-article content digest into every retrieved citation;
- binds the persisted `AnalysisResult` digest into the hash-chained audit record;
- verifies the complete audit chain before action review;
- uses an atomic one-review claim and also rejects replay visible in retained audit history;
- serializes SQLite audit sequence allocation with `BEGIN IMMEDIATE`;
- converts malformed persisted models into `IntegrityError`;
- records external-executor exceptions as an unknown outcome and blocks blind replay;
- removes the unsupported automatic-action configuration; every destructive action remains
  human-gated in this release;
- rejects future-dated evidence and ambiguous numeric/action extraction;
- closes SQLite connections deterministically;
- moves the composition root outside the application layer;
- hardens FastAPI request validation and error mapping;
- makes the Docker data path writable by the configured non-root user;
- strengthens architecture, secret, release, and static-security checks;
- removes handoff-only instructions and replaces claims with this evidence report.

## 5. Canonical validation matrix

| Gate | Status | Direct evidence |
|---|---:|---|
| Python bytecode compilation | PASS | `validation-logs/01-compileall.log` |
| Architecture dependency check | PASS | `validation-logs/02-architecture.log` |
| Repository high-confidence secret scan | PASS | `validation-logs/03-secret-scan.log` |
| Local AST static-security scan | PASS | `validation-logs/04-static-security.log` |
| Release metadata consistency | PASS | `validation-logs/05-release-metadata.log` |
| Generated JSON schemas match canonical models | PASS | generator rerun and clean schema diff |
| Unit, integration, API, adversarial, persistence, and concurrency tests | PASS | 72 tests |
| Resource-warning gate | PASS | tests run with `ResourceWarning` as error |
| Branch-aware coverage threshold | PASS | 96.11%; required 85% |
| Offline end-to-end demo | PASS | `validation-logs/09-demo.log` |
| FastAPI health smoke | PASS | `validation-logs/11-api-smoke.log` |
| Direct runtime dependency constraints in effective environment | PASS | Pydantic, PyYAML, Typer, Rich |
| sdist build | PASS | `resolveops-0.1.0rc2.tar.gz` |
| wheel build | PASS | `resolveops-0.1.0rc2-py3-none-any.whl` |
| Distribution path safety and metadata inspection | PASS | release validation logs |
| Fresh-venv wheel installation with dependency resolution disabled | PASS | packaging smoke; dependencies inherited from audited environment |
| Git object integrity after canonical commits | PASS | final `git fsck --full --strict` |
| Canonical Git working tree clean | PASS | final `git status --porcelain` |

A PASS for the local secret or static-security scripts means only that their documented,
limited checks passed. It is not equivalent to a comprehensive security review.

## 6. Blocked and untested gates

| Gate | Status | Reason |
|---|---:|---|
| Ruff formatter/linter | NOT TESTED | executable unavailable; package installation unavailable from configured registry |
| strict mypy | NOT TESTED | executable unavailable |
| `pip-audit` vulnerability resolution | NOT TESTED | executable/advisory access unavailable |
| `python -m build` frontend | NOT TESTED | `build` package unavailable; PEP 517 backend was invoked directly instead |
| Twine metadata check | NOT TESTED | executable unavailable; metadata was inspected independently |
| Fully isolated dependency-resolving installation | BLOCKED | package registry/DNS unavailable and internal registry lacked build dependencies |
| GitHub Actions execution on Python 3.11, 3.12, and 3.13 | NOT TESTED | no remote workflow run performed |
| Native local Python 3.11 and 3.12 execution | NOT TESTED | only Python 3.13.5 was available locally |
| Docker image build and runtime | NOT TESTED | Docker/Podman unavailable |
| macOS and Windows | NOT TESTED | Linux-only execution environment |
| Live CRM, billing, identity, or help-desk connectors | NOT TESTED | no production connector is included |
| Load, soak, chaos, and failover testing | NOT TESTED | outside this release-candidate environment |
| Fuzzing | NOT TESTED | no fuzzing engine available |
| Signed release provenance / Sigstore | NOT TESTED | no signing identity or external service used |

## 7. Residual risks and security boundary

1. The audit log is tamper-evident, not tamper-proof. A database administrator who can
   rewrite the complete chain can recompute hashes. Tail truncation also requires an
   externally anchored head to detect independently.
2. SQLite is a single-node persistence boundary. It is not suitable for active-active
   replicas or multi-region coordination.
3. Process termination after an external side effect but before recording its result can
   leave an approved analysis with no execution record. Replay remains blocked; manual
   reconciliation is required.
4. The mock executor is not a production payment or subscription adapter. A real adapter
   requires provider idempotency keys, authentication, authorization, timeout policy,
   reconciliation, and observability.
5. The API has no authentication, tenant isolation, rate limiting, or production secret
   management. It must not be exposed as a production service in this state.
6. The deterministic generator and lexical retrieval are reference baselines, not evidence
   of real-world quality on customer data.
7. Dependency vulnerability status is **UNKNOWN** because `pip-audit` could not run.

## 8. Transfer decision

The canonical repository is suitable for transfer to GitHub as an inspectable engineering
release candidate. It is not approved for production deployment, PyPI publication, or live
financial actions until the untested release gates are executed in public CI and the
production security boundary is implemented.
