"""Append-only post-action outcome verification use cases."""

from __future__ import annotations

from typing import cast

from resolveops.domain.audit import object_digest, verify_chain
from resolveops.domain.errors import IntegrityError, InvalidTransitionError, NotFoundError
from resolveops.domain.models import ActionExecution, ReviewState
from resolveops.domain.outcomes import (
    ActionOutcomeObservation,
    ActionOutcomeResult,
    ActionOutcomeState,
)
from resolveops.ports.interfaces import ActionOutcomeVerifier, IdempotentAuditStore, Store


class ActionOutcomeService:
    """Observe external outcomes without mutating the command execution ledger."""

    def __init__(self, *, store: Store, verifier: ActionOutcomeVerifier) -> None:
        self.store = store
        self.verifier = verifier

    def _verified_execution(self, execution_id: str) -> ActionExecution:
        execution = self.store.get_execution(execution_id)
        if execution is None:
            raise NotFoundError(f"execution not found: {execution_id}")

        events = self.store.list_audit()
        verify_chain(events)
        execution_events = [
            event
            for event in events
            if event.entity_id == execution.id
            and event.event_type
            in {
                "action.execution_claimed",
                "action.execution_attempt_started",
                "action.execution_updated",
            }
        ]
        execution_hash = object_digest(execution.model_dump(mode="json"))
        if (
            not execution_events
            or execution_events[-1].payload.get("execution_hash") != execution_hash
        ):
            raise IntegrityError("execution record does not match its audit evidence")

        approval = self.store.get_approval(execution.approval_id)
        if approval is None or approval.state is not ReviewState.APPROVED:
            raise IntegrityError("execution does not have a valid approved review")
        approval_events = [
            event
            for event in events
            if event.event_type == "analysis.reviewed" and event.entity_id == approval.id
        ]
        approval_hash = object_digest(approval.model_dump(mode="json"))
        if (
            len(approval_events) != 1
            or approval_events[0].payload.get("approval_hash") != approval_hash
        ):
            raise IntegrityError("approval record does not match its audit evidence")
        return execution

    @staticmethod
    def _validate_observation_identity(
        execution: ActionExecution,
        observation: ActionOutcomeObservation,
    ) -> None:
        if observation.execution_id != execution.id:
            raise IntegrityError("outcome observation belongs to a different execution")
        if execution.external_reference is None:
            raise InvalidTransitionError(
                "execution must have an external reference before outcome verification"
            )
        if observation.provider_reference != execution.external_reference:
            raise IntegrityError("outcome observation references a different provider operation")

    def _record_result(
        self,
        execution: ActionExecution,
        result: ActionOutcomeResult,
        *,
        audit_metadata: dict[str, object] | None = None,
        unique_event_key: str | None = None,
    ) -> ActionOutcomeObservation | None:
        observation = ActionOutcomeObservation(
            execution_id=execution.id,
            state=result.state,
            provider_reference=result.provider_reference,
            provider_status=result.provider_status,
            customer_reference=result.customer_reference,
            message=result.message,
        )
        self._validate_observation_identity(execution, observation)
        payload: dict[str, object] = {
            "execution_id": execution.id,
            "provider_reference": observation.provider_reference,
            "state": observation.state.value,
            "provider_status": observation.provider_status,
            "action_hash": object_digest(execution.action.model_dump(mode="json")),
            "idempotency_key_hash": object_digest(execution.idempotency_key),
            "observation": observation.model_dump(mode="json"),
            "observation_hash": object_digest(observation.model_dump(mode="json")),
        }
        if audit_metadata:
            payload.update(audit_metadata)
        if unique_event_key is None:
            self.store.append_audit_event("action.outcome_observed", execution.id, payload)
            return observation
        event_store = cast(IdempotentAuditStore, self.store)
        event = event_store.append_audit_event_once(
            unique_event_key,
            "action.outcome_observed",
            execution.id,
            payload,
        )
        return observation if event is not None else None

    def observe(self, execution_id: str) -> ActionOutcomeObservation:
        """Append one current provider observation for an already-identified operation."""
        execution = self._verified_execution(execution_id)
        if execution.external_reference is None:
            raise InvalidTransitionError(
                "execution must be reconciled to an external reference before outcome verification"
            )

        try:
            result = self.verifier.verify(execution)
        except Exception:
            result = ActionOutcomeResult(
                state=ActionOutcomeState.UNKNOWN,
                provider_reference=execution.external_reference,
                provider_status=execution.provider_status,
                message="Outcome verification failed; provider state requires investigation.",
            )
        observation = self._record_result(execution, result)
        assert observation is not None
        return observation

    def observe_external(
        self,
        execution_id: str,
        *,
        stripe_event_id: str,
        stripe_event_type: str,
        stripe_signature_timestamp: int,
        unique_event_key: str,
    ) -> ActionOutcomeObservation | None:
        """Use an authenticated Stripe event only as a trigger for an exact current-state read.

        Provider-read failures deliberately propagate so the webhook event remains unclaimed and the
        ingress can ask Stripe to retry. Manual observations use ``observe`` and may instead record
        an explicit UNKNOWN fact.
        """
        execution = self._verified_execution(execution_id)
        if execution.external_reference is None:
            raise InvalidTransitionError(
                "execution must be reconciled to an external reference before outcome verification"
            )
        result = self.verifier.verify(execution)
        return self._record_result(
            execution,
            result,
            audit_metadata={
                "stripe_event_id": stripe_event_id,
                "stripe_event_type": stripe_event_type,
                "stripe_signature_timestamp": stripe_signature_timestamp,
            },
            unique_event_key=unique_event_key,
        )

    def list_observations(self, execution_id: str) -> list[ActionOutcomeObservation]:
        """Return verified append-only observations in audit-sequence order."""
        execution = self._verified_execution(execution_id)
        events = self.store.list_audit()
        verify_chain(events)
        observations: list[ActionOutcomeObservation] = []
        expected_action_hash = object_digest(execution.action.model_dump(mode="json"))
        expected_key_hash = object_digest(execution.idempotency_key)
        for event in events:
            if event.event_type != "action.outcome_observed" or event.entity_id != execution.id:
                continue
            raw = event.payload.get("observation")
            if not isinstance(raw, dict):
                raise IntegrityError(
                    "outcome audit event does not contain a structured observation"
                )
            try:
                observation = ActionOutcomeObservation.model_validate(raw)
            except (ValueError, TypeError) as exc:
                raise IntegrityError("outcome audit event contains an invalid observation") from exc
            self._validate_observation_identity(execution, observation)
            if (
                event.payload.get("execution_id") != execution.id
                or event.payload.get("provider_reference") != observation.provider_reference
                or event.payload.get("state") != observation.state.value
                or event.payload.get("provider_status") != observation.provider_status
                or event.payload.get("action_hash") != expected_action_hash
                or event.payload.get("idempotency_key_hash") != expected_key_hash
                or event.payload.get("observation_hash")
                != object_digest(observation.model_dump(mode="json"))
            ):
                raise IntegrityError("outcome observation does not match its audit evidence")
            observations.append(observation)
        return observations

    def latest_observation(self, execution_id: str) -> ActionOutcomeObservation | None:
        """Return the most recent observation without implying permanence or terminality."""
        observations = self.list_observations(execution_id)
        return observations[-1] if observations else None
