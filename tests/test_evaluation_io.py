import json
from decimal import Decimal

import pytest

from resolveops.domain.models import Outcome, Ticket
from resolveops.evaluation import export_inferenceledger_events, load_cases


def test_load_cases(tmp_path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        '{"id":"x","ticket":{"customer_id":"c","message":"hello"},'
        '"customer":{"id":"c"},"expected_intent":"unknown"}\n',
        encoding="utf-8",
    )
    cases = load_cases(path)
    assert cases[0].id == "x"


def test_load_cases_reports_line(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1"):
        load_cases(path)


def test_export_outcomes(service, tmp_path) -> None:
    ticket = Ticket(customer_id="cust_1", message="What is policy?")
    service.analyze(ticket)
    service.record_outcome(
        Outcome(
            ticket_id=ticket.id,
            resolved=True,
            escalated=False,
            model_cost_usd=Decimal("0.001234"),
        )
    )
    path = tmp_path / "events.jsonl"
    export_inferenceledger_events(service, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["task_id"] == ticket.id
    assert payload["cost_usd"] == "0.001234"


def test_export_type_guard(tmp_path) -> None:
    with pytest.raises(TypeError):
        export_inferenceledger_events(object(), tmp_path / "x")
