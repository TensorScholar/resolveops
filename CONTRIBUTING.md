# Contributing

ResolveOps is maintained as a small, evidence-driven reference implementation. Changes should preserve its narrow product boundary and make behavior easier to inspect, test, and reason about.

## Development setup

Use Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,web]'
```

Run the primary quality gates before opening a pull request:

```bash
ruff format --check .
ruff check .
mypy src/resolveops
python scripts/check_architecture.py
python scripts/secret_scan.py
python scripts/security_scan.py
pytest --cov=resolveops --cov-branch
```

Changes that affect generated models or release metadata should also run the relevant schema and release checks.

## Change expectations

- Include tests for behavior changes and regressions.
- Preserve the dependency rules documented in [`docs/architecture.md`](docs/architecture.md).
- Keep business policy deterministic and separate from response generation.
- Do not introduce hidden network, credential, or model dependencies into the domain layer.
- Prefer minimal fixes over broad refactors when addressing security or integrity defects.

## Security-sensitive changes

A change that affects approval, execution, persistence integrity, audit evidence, authentication boundaries, or external side effects should include:

1. a concrete threat or failure scenario;
2. a regression test that demonstrates the previous failure when practical;
3. the smallest implementation change that closes the failure;
4. independent review before merge;
5. updated residual-risk or release documentation when the boundary changes.

Large architectural changes should be recorded as an ADR under [`docs/adr/`](docs/adr/).

## Scope discipline

ResolveOps is intentionally not a general agent platform. New capabilities should strengthen the existing evidence-grounded support workflow rather than expand the project into a broad plugin or control-plane framework.