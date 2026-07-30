# Architecture

ResolveOps is a modular monolith.

```text
CLI / FastAPI
     |
application service
     |
domain functions and models
     |
ports
  /      \
SQLite   deterministic generator
memory   mock action executor
```

Dependency rules:

- `domain` imports only the standard library and Pydantic schema types.
- `application` imports domain and ports.
- `ports` import domain types.
- `adapters` implement ports.
- `web` and `cli` compose the application.
- no domain module imports FastAPI, SQLite, Typer, or a vendor SDK.

Vertical slices are preferred over empty architecture layers. A new action must include:

1. domain schema;
2. policy behavior;
3. executor implementation;
4. tests;
5. audit event;
6. documentation.
