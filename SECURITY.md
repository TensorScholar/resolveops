# Security policy

Report vulnerabilities privately to the repository owner. Do not include live credentials, customer data, exploit details, or other sensitive information in public issues.

ResolveOps is a reference implementation and release candidate, not a complete production security boundary. The bundled mock action adapter must not be wired directly to production billing or subscription systems.

A production deployment requires, at minimum:

- authenticated user and service identities;
- explicit authorization for high-impact actions;
- tenant isolation;
- production secret management;
- rate limiting and abuse controls;
- provider-side idempotency and reconciliation;
- externally anchored or signed audit evidence where tamper resistance is required;
- operational monitoring and incident response.

For the current threat assumptions, controls, and residual risks, see [`docs/security-model.md`](docs/security-model.md).