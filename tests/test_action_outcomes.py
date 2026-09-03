from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from resolveops.application.outcomes import ActionOutcomeService
from resolveops.domain.audit import make_event
from resolveops.domain.errors import IntegrityError
from resolveops.domain.models import ExecutionState, Ticket
from resolveops.domain.outcomes import ActionOutcomeResult, ActionOutcomeState


@dataclass
class SequencedVerifier:
    results: list[ActionOutcomeResult] = field(default_factory=list)
    error: Exception | None = None

    def verify(self, execution):
        if self.error is not None:
            raise self.error
        assert self.results
        result = self.results.pop(0)
        return result


def successful_execution(service):
    analysis = service.analyze(
        Ticket(
            customer_id="cust_1",
            message="Refund $49",
            payment_reference="pay_cust_1",
        )
    )
    _, execution = service.review(
        analysis.id,
        reviewer="manager@example.com",
        approve=True,
    )
    assert execution is not None
    assert execution.state is ExecutionState.SUCCEEDED
    assert execution.external_reference is not None
    return execution


def test_execution_success_and_customer_outcome_are_separate(service) -> None:
    execution = successful_execution(service)
    verifier = SequencedVerifier(
        results=[
            ActionOutcomeResult(
                state=ActionOutcomeState.VERIFIED,
                provider_reference=execution.external_reference,
                provider_status="succeeded",
                message="Provider currently reports success.",
            ),
            ActionOutcomeResult(
                state=ActionOutcomeState.FAILED,
                provider_reference=execution.external_reference,
                provider_status="failed",
                message="Provider later reports returned funds.",
            ),
        ]
    )
    outcomes = ActionOutcomeService(store=service.store, verifier=verifier)

    first = outcomes.observe(execution.id)
    second = outcomes.observe(execution.id)

    assert first.state is ActionOutcomeState.VERIFIED
    assert second.state is ActionOutcomeState.FAILED
    assert service.store.get_execution(execution.id) == execution
    assert service.store.get_execution(execution.id).state is ExecutionState.SUCCEEDED
    assert outcomes.list_observations(execution.id) == [first, second]
    assert outcomes.latest_observation(execution.id) == second
    service.verify_audit()


def test_verifier_exception_is_audited_as_unknown(service) -> None:
    execution = successful_execution(service)
    outcomes = ActionOutcomeService(
        store=service.store,
        verifier=SequencedVerifier(error=TimeoutError("provider unavailable")),
    )

    observation = outcomes.observe(execution.id)

    assert observation.state is ActionOutcomeState.UNKNOWN
    assert observation.provider_reference == execution.external_reference
    assert outcomes.latest_observation(execution.id) == observation
    service.verify_audit()


def test_verifier_cannot_substitute_provider_operation(service) -> None:
    execution = successful_execution(service)
    outcomes = ActionOutcomeService(
        store=service.store,
        verifier=SequencedVerifier(
            results=[
                ActionOutcomeResult(
                    state=ActionOutcomeState.VERIFIED,
                    provider_reference="refund_different",
                    provider_status="succeeded",
                    message="wrong operation",
                )
            ]
        ),
    )
    before = len(service.store.list_audit())

    with pytest.raises(IntegrityError, match="different provider operation"):
        outcomes.observe(execution.id)

    assert len(service.store.list_audit()) == before


def test_outcome_projection_metadata_must_match_canonical_observation(service) -> None:
    execution = successful_execution(service)
    outcomes = ActionOutcomeService(
        store=service.store,
        verifier=SequencedVerifier(
            results=[
                ActionOutcomeResult(
                    state=ActionOutcomeState.VERIFIED,
                    provider_reference=execution.external_reference,
                    provider_status="succeeded",
                    message="Provider currently reports success.",
                )
            ]
        ),
    )
    outcomes.observe(execution.id)

    event = service.store.audit[-1]
    payload = dict(event.payload)
    payload["state"] = ActionOutcomeState.FAILED.value
    service.store.audit[-1] = make_event(
        sequence=event.sequence,
        event_type=event.event_type,
        entity_id=event.entity_id,
        payload=payload,
        previous_hash=event.previous_hash,
        occurred_at=event.occurred_at,
    )

    with pytest.raises(IntegrityError, match="does not match its audit evidence"):
        outcomes.list_observations(execution.id)
