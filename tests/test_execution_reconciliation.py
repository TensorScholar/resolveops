from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.sqlite import SQLiteStore
from resolveops.application.service import ResolveOpsService
from resolveops.domain.models import (
    ActionExecution,
    ActionProposal,
    Approval,
    CustomerProfile,
    ExecutionResult,
    ExecutionState,
    KnowledgeArticle,
    Ticket,
)


@dataclass
class FakeProvider:
    effects: dict[str, str] = field(default_factory=dict)
    effect_count: int = 0

    def apply(self, idempotency_key: str) -> str:
        reference = self.effects.get(idempotency_key)
        if reference is None:
            reference = f"provider_ref_{len(self.effects) + 1}"
            self.effects[idempotency_key] = reference
            self.effect_count += 1
        return reference


class CrashAfterSideEffectExecutor:
    def __init__(self, provider: FakeProvider) -> None:
        self.provider = provider

    def execute(
        self,
        action: ActionProposal,
        *,
        approval: Approval,
        idempotency_key: str,
    ) -> ExecutionResult:
        del action, approval
        self.provider.apply(idempotency_key)
        raise SystemExit("simulated process termination after provider side effect")

    def reconcile(self, execution: ActionExecution) -> ExecutionResult:
        reference = self.provider.effects.get(execution.idempotency_key)
        if reference is None:
            return ExecutionResult(
                state=ExecutionState.UNKNOWN,
                message="Provider has no evidence for this operation.",
            )
        return ExecutionResult(
            state=ExecutionState.SUCCEEDED,
            message="Provider confirmed the original operation.",
            external_reference=reference,
            provider_status="succeeded",
        )


class TimeoutAfterSideEffectExecutor(CrashAfterSideEffectExecutor):
    def execute(
        self,
        action: ActionProposal,
        *,
        approval: Approval,
        idempotency_key: str,
    ) -> ExecutionResult:
        del action, approval
        self.provider.apply(idempotency_key)
        raise TimeoutError("simulated response loss")


def build_service(path, executor) -> ResolveOpsService:
    service = ResolveOpsService(
        store=SQLiteStore(path),
        generator=DeterministicResponseGenerator(),
        action_executor=executor,
    )
    service.seed_customer(CustomerProfile(id="c"))
    service.seed_article(
        KnowledgeArticle(
            id="k",
            title="Refund policy",
            body="Refunds require approval.",
            source_uri="kb://refund",
            owner="support",
        )
    )
    return service


def test_process_termination_leaves_recoverable_pending_execution(tmp_path) -> None:
    database = tmp_path / "crash.db"
    provider = FakeProvider()
    first = build_service(database, CrashAfterSideEffectExecutor(provider))
    analysis = first.analyze(Ticket(customer_id="c", message="Refund $10"))

    with pytest.raises(SystemExit, match="simulated process termination"):
        first.review(analysis.id, reviewer="manager@example.com", approve=True)

    persisted = SQLiteStore(database)
    executions = persisted.list_executions()
    assert len(executions) == 1
    pending = executions[0]
    assert pending.state is ExecutionState.PENDING
    assert pending.attempt_count == 0
    assert persisted.get_approval(pending.approval_id) is not None
    assert provider.effect_count == 1

    restarted = ResolveOpsService(
        store=persisted,
        generator=DeterministicResponseGenerator(),
        action_executor=CrashAfterSideEffectExecutor(provider),
    )
    restarted.verify_audit()
    recovered = restarted.reconcile_execution(pending.id)

    assert recovered.state is ExecutionState.SUCCEEDED
    assert recovered.external_reference == provider.effects[pending.idempotency_key]
    assert recovered.attempt_count == 1
    assert provider.effect_count == 1
    restarted.verify_audit()


def test_timeout_is_unknown_until_provider_reconciliation(tmp_path) -> None:
    database = tmp_path / "timeout.db"
    provider = FakeProvider()
    service = build_service(database, TimeoutAfterSideEffectExecutor(provider))
    analysis = service.analyze(Ticket(customer_id="c", message="Refund $10"))

    _, uncertain = service.review(
        analysis.id,
        reviewer="manager@example.com",
        approve=True,
    )
    assert uncertain is not None
    assert uncertain.state is ExecutionState.UNKNOWN
    assert uncertain.attempt_count == 1
    assert service.metrics()["actions_requiring_reconciliation"] == 1

    reconciled = service.reconcile_execution(uncertain.id)
    assert reconciled.state is ExecutionState.SUCCEEDED
    assert reconciled.attempt_count == 2
    assert provider.effect_count == 1
    assert service.metrics()["actions_requiring_reconciliation"] == 0
