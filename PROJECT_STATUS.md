# Project status

ResolveOps `0.1.0rc2` is a hardened engineering release candidate.

The source has locally reproduced tests for policy enforcement, approval replay prevention,
concurrent SQLite audit appends, corrupt persisted JSON, strict API request validation,
package build, and wheel installation. The exact evidence boundary is recorded in
[`AUDIT_REPORT.md`](AUDIT_REPORT.md).

The following remain outside the evidence boundary: public GitHub Actions execution across
Python 3.11/3.12/3.13, live connector behavior, authentication and tenant isolation,
container runtime validation, operating-system portability, external pilot results, and
production operations.

Do not describe this release as production-ready.
