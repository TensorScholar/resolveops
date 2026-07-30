# Contributing

Use Python 3.11 or newer. Run:

```bash
ruff format --check .
ruff check .
mypy src/resolveops
pytest --cov=resolveops --cov-branch
```

Changes must include tests and must preserve the dependency rules in
`docs/architecture.md`.
