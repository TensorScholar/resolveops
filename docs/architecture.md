# Architecture

ResolveOps is a modular monolith.

```text
CLI / FastAPI / composition root
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
- `application` imports domain and ports, never adapters.
- `ports` import domain types.
- `adapters` implement ports.
- the top-level composition root selects adapters for `web`, `cli`, and demos.
- no domain module imports FastAPI, SQLite, Typer, or a vendor SDK.

Vertical slices are preferred over empty architecture layers. A new action must include:

1. domain schema;
2. policy behavior;
3. executor implementation;
4. tests;
5. audit event;
6. documentation.
