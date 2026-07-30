"""Fixture-based evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from resolveops.domain.models import EvaluationCase


def load_cases(path: str | Path) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                cases.append(EvaluationCase.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"invalid evaluation case at line {line_number}") from exc
    return cases


def export_inferenceledger_events(service: object, path: str | Path) -> None:
    from resolveops.application.service import ResolveOpsService

    if not isinstance(service, ResolveOpsService):
        raise TypeError("service must be ResolveOpsService")
    output = Path(path)
    with output.open("w", encoding="utf-8") as handle:
        for outcome in service.store.list_outcomes():
            payload = {
                "task_id": outcome.ticket_id,
                "success": outcome.resolved,
                "cost_usd": str(outcome.model_cost_usd),
                "human_minutes": outcome.human_minutes,
                "timestamp": outcome.recorded_at.isoformat(),
            }
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
