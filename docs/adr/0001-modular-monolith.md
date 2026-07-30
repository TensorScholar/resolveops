# ADR 0001: Modular monolith

## Decision

Use a modular monolith with hexagonal boundaries and a functional core / imperative shell.

## Rationale

The product needs strict contracts and adapter flexibility, but does not need distributed
transactions, service discovery, message brokers, or separate deployment units.

## Consequences

- adapters are replaceable;
- tests can run offline;
- deployment remains one process;
- scaling boundaries may be extracted later only with evidence.
