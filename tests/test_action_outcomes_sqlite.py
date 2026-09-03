from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from resolveops.adapters.actions import MockActionExecutor
from resolveops.adapters.billing import MemoryBillingReader
from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.sqlite import SQLiteStore
from resolveops.application.outcomes import ActionOutcomeService
from resolveops.application.service import ResolveOpsService
from resolveops.domain.models import (
    CustomerProfile,
    ExecutionState,
    KnowledgeArticle,
    PaymentSnapshot,
    Ticket,
)
from resolveops.domain.outcomes import ActionOutcomeResult, ActionOutcomeState


class FixedVerifier:
    def __init__(self, result: ActionOutcomeResult) -> None:
        self.result = result

    def verify(self, execution):
        del execution
        return self.result


def _service(path: Path, billing_reader: MemoryBillingReader) -> ResolveOpsService:
    return ResolveOpsService(
        store=SQLiteStore(path),
        generator=DeterministicResponseGenerator(),
        action_executor=MockActionExecutor(),
        billing_reader=billing_reader,
    )


def test_action_outcome_observations_survive_sqlite_restart(tmp_path: Path) -> None:
    database = tmp_path / "resolveops.db"
    billing_reader = MemoryBillingReader(
        (
            PaymentSnapshot(
                id="pay_restart",
                customer_id="cust_restart",
                amount=Decimal("100.00"),
                amount_refunded=Decimal("0.00"),
                currency="usd",
                refundable=True,
                status="succeeded",
            ),
        )
    )
    first_service = _service(database, billing_reader)
    first_service.seed_customer(
        CustomerProfile(
            id="cust_restart",
            plan="pro",
            lifetime_value=Decimal("1000.00"),
            account_age_days=365,
        )
    )
    first_service.seed_article(
        KnowledgeArticle(
            id="kb_restart_refund",
            title="Refund policy",
            body="Refunds up to $250 require human approval.",
            source_uri="kb://refund/restart",
            owner="support",
            updated_at=datetime.now(UTC),
        )
    )
    analysis = first_service.analyze(
        Ticket(
            customer_id="cust_restart",
            message="Please refund $40.00",
            payment_reference="pay_restart",
        )
    )
    _, execution = first_service.review(
        analysis.id,
        reviewer="manager@example.com",
        approve=True,
    )
    assert execution is not None
    assert execution.state is ExecutionState.SUCCEEDED
    assert execution.external_reference is not None

    first_outcomes = ActionOutcomeService(
        store=first_service.store,
        verifier=FixedVerifier(
            ActionOutcomeResult(
                state=ActionOutcomeState.VERIFIED,
                provider_reference=execution.external_reference,
                provider_status="succeeded",
                message="Provider currently verifies the refund.",
            )
        ),
    )
    first_observation = first_outcomes.observe(execution.id)
    first_service.verify_audit()

    restarted_service = _service(database, billing_reader)
    restarted_outcomes = ActionOutcomeService(
        store=restarted_service.store,
        verifier=FixedVerifier(
            ActionOutcomeResult(
                state=ActionOutcomeState.FAILED,
                provider_reference=execution.external_reference,
                provider_status="failed",
                message="Provider later reports the refund failed.",
            )
        ),
    )

    assert restarted_outcomes.list_observations(execution.id) == [first_observation]
    second_observation = restarted_outcomes.observe(execution.id)
    assert second_observation.state is ActionOutcomeState.FAILED
    assert restarted_outcomes.list_observations(execution.id) == [
        first_observation,
        second_observation,
    ]
    assert restarted_outcomes.latest_observation(execution.id) == second_observation
    assert restarted_service.store.get_execution(execution.id) == execution
    restarted_service.verify_audit()
