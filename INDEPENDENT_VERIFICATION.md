# Independent verification

This handoff was generated and validated locally before delivery.

The release process verifies:

- source compilation;
- Ruff formatting and lint;
- strict mypy;
- pytest and branch-aware coverage;
- offline demo;
- SQLite persistence and audit verification;
- optional FastAPI smoke;
- wheel and sdist creation;
- installation from the wheel into an isolated virtual environment;
- package metadata;
- checksums and ZIP integrity.

The validation report in `release/` contains exact command outputs and limitations.
