import pytest

from resolveops.domain.errors import NotFoundError
from resolveops.domain.models import (
    Disposition,
    EvaluationSummary,
    Outcome,
    Ticket,
)


def test_unknown_customer_fails(service) -> None:
    with pytest.raises(NotFoundError):
        service.analyze(Ticket(customer_id="missing", message="hello"))


def test_seed_article_type_guard(service) -> None:
    with pytest.raises(TypeError):
        service.seed_article(object())


def test_record_unknown_outcome_fails(service) -> None:
    with pytest.raises(NotFoundError):
        service.record_outcome(
            Outcome(ticket_id="missing", resolved=False, escalated=True)
        )


def test_missing_evidence_escalates(service) -> None:
    service.store.articles.clear()
    result = service.analyze(
        Ticket(customer_id="cust_1", message="What is the password policy?")
    )
    assert result.disposition is Disposition.ESCALATE
    assert result.confidence == 0.25


def test_metrics_empty() -> None:
    from resolveops.adapters.actions import MockActionExecutor
    from resolveops.adapters.generator import DeterministicResponseGenerator
    from resolveops.adapters.memory import MemoryStore
    from resolveops.application.service import ResolveOpsService

    fresh = ResolveOpsService(
        store=MemoryStore(),
        generator=DeterministicResponseGenerator(),
        action_executor=MockActionExecutor(),
    )
    assert fresh.metrics()["resolution_rate"] == 0.0


def test_empty_evaluation(service) -> None:
    summary = service.evaluate_cases([])
    assert isinstance(summary, EvaluationSummary)
    assert summary.cases == 0
    assert summary.citation_recall == 1.0
