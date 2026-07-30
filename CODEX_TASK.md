# ResolveOps Codex handoff task

Act as a senior applied-AI engineer, product engineer, security reviewer, and release engineer.

## Goal

Independently audit and harden the included `candidate-source/` repository. Preserve its
product thesis: an evidence-grounded support operations system, not a generic chatbot.

## Constraints

- Work only inside `candidate-source`.
- Create a local branch named `review/resolveops-v0.1`.
- Do not push, merge, tag, publish, open a pull request, or modify GitHub.
- Do not add LangChain, a vector database, Kubernetes, Redis, Celery, or microservices.
- Do not add a dashboard framework.
- Do not introduce a network LLM requirement.
- Do not weaken tests or coverage thresholds.
- Do not claim production readiness.

## Required audit

1. Verify source integrity and Git status.
2. Review architecture dependency direction.
3. Inspect evidence freshness, escalation, approval transitions, audit integrity,
   SQLite behavior, exports, and API validation.
4. Test adversarial cases:
   - no evidence;
   - expired evidence;
   - oversized refund;
   - unknown refund amount;
   - approval replay attempts;
   - audit tampering;
   - malformed persisted JSON;
   - concurrent SQLite writes;
   - untrusted action executor behavior;
   - prompt text that tries to override policy.
5. Run Ruff, strict mypy, pytest, branch coverage, pip-audit, build, wheel smoke,
   schema checks, compileall, demo, and API smoke.
6. Keep implementation minimal. Fix only demonstrated defects.
7. Produce focused local commits and a final review export ZIP with raw logs,
   source ZIP, Git bundle, diff, wheel, sdist, SBOM, manifest, and checksums.

## Definition of done

- deterministic offline demo;
- no action without an explicit valid transition;
- missing or stale evidence never produces an automatic destructive action;
- strict schemas reject unknown fields;
- audit chain detects mutation;
- clean wheel installation;
- all validation results reported as PASS / FAIL / NOT RUN;
- working tree clean;
- nothing published.

Stop after creating the review export.
