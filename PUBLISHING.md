# Publishing

Before publishing Resolveops:

1. public CI is green on every supported Python version;
2. Ruff, strict mypy, pytest, branch coverage, pip-audit, build, and wheel smoke pass;
3. generated schemas match source;
4. release artefacts come from the tagged commit;
5. SBOM, manifest, checksums, and validation report are attached;
6. limitations and status are honest;
7. no real customer data or credentials are present.

PyPI publication is manual in v0.1.
