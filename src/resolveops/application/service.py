"""ResolveOps use cases."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from resolveops.domain.audit import object_digest, verify_chain
from resolveops.domain.errors import (
    IntegrityError,
    InvalidTransitionError,
    NotFoundError,
    PolicyDeniedError,
)
from resolveops.domain.execution import (
    apply_execution_result,
    begin_execution_attempt,
    build_idempotency_key,
)
from resolveops.domain.models import (
    ActionExecution,
    AnalysisResult,
    Approval,
    AuditEvent,
    AuditEventDraft,
    Citation,
    CustomerProfile,
    Disposition,
    EvaluationCase,
    EvaluationSummary,
    ExecutionResult,
    ExecutionState,
    Outcome,
    PolicySettings,
    ReviewState,
    Ticket,
)
from resolveops.domain.policy import evaluate
from resolveops.domain.retrieval import retrieve
from resolveops.domain.triage import classify_intent, propose_action
from resolveops.ports.interfaces import ActionExecutor, ResponseGenerator, Store


class ResolveOpsService:
    def __init__(
        self,
        *,
        store: Store,
        generator: ResponseGenerator,
        action_executor: ActionExecutor,
        policy: PolicySettings | None = None,
    ) -> None:
        self.store = store
        self.generator = generator
        self.action_executor = action_executor
        self.policy = policy or PolicySettings()

    def _audit(self, event_type: str, entity_id: str, payload: dict[str, object]) -> None:
        self.store.append_audit_event(event_type, entity_id, payload)

    def _verify_analysis_integrity(self, analysis: AnalysisResult) -> list[AuditEvent]:
        events = self.store.list_audit()
        verify_chain(events)
        matches = [
            event
            for event in events
            if event.event_type == "ticket.analyzed" and event.entity_id == analysis.id
        ]
        expected = object_digest(analysis.model_dump(mode="json"))
        if len(matches) != 1 or matches[0].payload.get("analysis_hash") != expected:
            raise IntegrityError("analysis record does not match its audit evidence")
        return events

    def _verify_approval_integrity(self, approval: Approval) -> None:
        events = self.store.list_audit()
        verify_chain(events)
        matches = [
            event
            for event in events
            if event.event_type == "analysis.reviewed" and event.entity_id == approval.id
        ]
        expected = object_digest(approval.model_dump(mode="json"))
        if len(matches) != 1 or matches[0].payload.get("approval_hash") != expected:
            raise IntegrityError("approval record does not match its audit evidence")

    def _verify_execution_integrity(self, execution: ActionExecution) -> None:
        events = self.store.list_audit()
        verify_chain(events)
        matches = [
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
        expected = object_digest(execution.model_dump(mode="json"))
        if not matches or matches[-1].payload.get("execution_hash") != expected:
            raise IntegrityError("execution record does not match its audit evidence")

    def _approved_review_for_execution(self, execution: ActionExecution) -> Approval:
        approval = self.store.get_approval(execution.approval_id)
        if approval is None:
            raise IntegrityError("execution does not have a persisted approval")
        self._verify_approval_integrity(approval)
        if approval.state is not ReviewState.APPROVED:
            raise IntegrityError("execution does not have a valid approved review")
        return approval

    def _current_citations(self, analysis: AnalysisResult) -> tuple[Citation, ...]:
        now = datetime.now(UTC)
        articles = {article.id: article for article in self.store.list_articles()}
        current: list[Citation] = []
        for citation in analysis.citations:
            article = articles.get(citation.article_id)
            if article is None or not article.approved:
                continue
            if article.updated_at > now:
                continue
            if article.expires_at is not None and article.expires_at <= now:
                continue
            if (
                article.updated_at != citation.updated_at
                or article.source_uri != citation.source_uri
                or citation.article_hash is None
                or object_digest(article.model_dump(mode="json")) != citation.article_hash
            ):
                continue
            current.append(citation)
        return tuple(current)

    @staticmethod
    def _analysis_audit(ticket: Ticket, analysis: AnalysisResult) -> AuditEventDraft:
        return AuditEventDraft(
            event_type="ticket.analyzed",
            entity_id=analysis.id,
            payload={
                "ticket_id": ticket.id,
                "ticket_hash": object_digest(ticket.model_dump(mode="json")),
                "intent": analysis.intent.value,
                "disposition": analysis.disposition.value,
                "citation_ids": [item.article_id for item in analysis.citations],
                "analysis_hash": object_digest(analysis.model_dump(mode="json")),
            },
        )

    @staticmethod
    def _execution_audit(execution: ActionExecution, event_type: str) -> AuditEventDraft:
        return AuditEventDraft(
            event_type=event_type,
            entity_id=execution.id,
            payload={
                "analysis_id": execution.analysis_id,
                "approval_id": execution.approval_id,
                "state": execution.state.value,
                "attempt_count": execution.attempt_count,
                "external_reference": execution.external_reference,
                "provider_status": execution.provider_status,
                "action_hash": object_digest(execution.action.model_dump(mode="json")),
                "idempotency_key_hash": object_digest(execution.idempotency_key),
                "execution_hash": object_digest(execution.model_dump(mode="json")),
            },
        )

    def _begin_execution_attempt(self, execution: ActionExecution) -> ActionExecution:
        updated = begin_execution_attempt(execution)
        self.store.update_execution(
            updated,
            audit_event=self._execution_audit(updated, "action.execution_attempt_started"),
        )
        return updated

    def _persist_execution_result(
        self,
        execution: ActionExecution,
        result: ExecutionResult,
    ) -> ActionExecution:
        updated = apply_execution_result(execution, result)
        self.store.update_execution(
            updated,
            audit_event=self._execution_audit(updated, "action.execution_updated"),
        )
        return updated

    def seed_customer(self, customer: CustomerProfile) -> None:
        self.store.put_customer(customer)

    def seed_article(self, article: object) -> None:
        from resolveops.domain.models import KnowledgeArticle

        if not isinstance(article, KnowledgeArticle):
            raise TypeError("article must be KnowledgeArticle")
        self.store.put_article(article)

    def analyze(self, ticket: Ticket) -> AnalysisResult:
        incoming_ticket_hash = object_digest(ticket.model_dump(mode="json"))
        existing = self.store.get_analysis_for_ticket(ticket.id)
        if existing is not None:
            persisted_ticket = self.store.get_ticket(ticket.id)
            if persisted_ticket is None:
                raise IntegrityError("analysis claim references a missing ticket")
            if object_digest(persisted_ticket.model_dump(mode="json")) != incoming_ticket_hash:
                raise IntegrityError("ticket id is already bound to different content")
            self._verify_analysis_integrity(existing)
            return existing

        persisted_ticket = self.store.get_ticket(ticket.id)
        if (
            persisted_ticket is not None
            and object_digest(persisted_ticket.model_dump(mode="json")) != incoming_ticket_hash
        ):
            raise IntegrityError("ticket id is already bound to different content")

        customer = self.store.get_customer(ticket.customer_id)
        if customer is None:
            raise NotFoundError(f"customer not found: {ticket.customer_id}")
        intent = classify_intent(ticket.message)
        action = propose_action(ticket, intent)
        citations = retrieve(ticket.message, self.store.list_articles())
        summary, draft, confidence = self.generator.generate(
            ticket=ticket,
            customer=customer,
            citations=citations,
            intent=intent.value,
        )
        decision = evaluate(
            confidence=confidence,
            citations=citations,
            action=action,
            settings=self.policy,
        )
        analysis = AnalysisResult(
            ticket_id=ticket.id,
            intent=intent,
            summary=summary,
            draft_reply=draft,
            citations=citations,
            confidence=confidence,
            disposition=decision.disposition,
            disposition_reasons=decision.reasons,
            proposed_action=action,
        )
        persisted = self.store.record_analysis(
            ticket,
            analysis,
            audit_event=self._analysis_audit(ticket, analysis),
        )
        if persisted.id != analysis.id:
            self._verify_analysis_integrity(persisted)
        return persisted

    def review(
        self,
        analysis_id: str,
        *,
        reviewer: str,
        approve: bool,
        note: str = "",
    ) -> tuple[Approval, ActionExecution | None]:
        analysis = self.store.get_analysis(analysis_id)
        if analysis is None:
            raise NotFoundError(f"analysis not found: {analysis_id}")
        events = self._verify_analysis_integrity(analysis)
        if any(
            event.event_type == "analysis.reviewed"
            and event.payload.get("analysis_id") == analysis.id
            for event in events
        ):
            raise InvalidTransitionError("analysis has already been reviewed")
        if analysis.disposition is Disposition.DENY:
            raise PolicyDeniedError("denied analysis cannot be approved")
        if analysis.proposed_action is None:
            raise InvalidTransitionError("analysis has no action to review")
        if analysis.disposition is not Disposition.REVIEW_REQUIRED:
            raise InvalidTransitionError("analysis is not waiting for review")
        if approve:
            decision = evaluate(
                confidence=analysis.confidence,
                citations=self._current_citations(analysis),
                action=analysis.proposed_action,
                settings=self.policy,
            )
            if not decision.action_allowed:
                reason = decision.reasons[0] if decision.reasons else "policy_denied_action"
                raise PolicyDeniedError(f"action is not allowed: {reason}")

        approval = Approval(
            analysis_id=analysis.id,
            reviewer=reviewer,
            state=ReviewState.APPROVED if approve else ReviewState.REJECTED,
            note=note,
        )
        review_event = AuditEventDraft(
            event_type="analysis.reviewed",
            entity_id=approval.id,
            payload={
                "analysis_id": analysis.id,
                "state": approval.state.value,
                "reviewer": reviewer,
                "analysis_hash": object_digest(analysis.model_dump(mode="json")),
                "approval_hash": object_digest(approval.model_dump(mode="json")),
            },
        )

        execution: ActionExecution | None = None
        audit_events: tuple[AuditEventDraft, ...] = (review_event,)
        if approve:
            execution = ActionExecution(
                analysis_id=analysis.id,
                approval_id=approval.id,
                action=analysis.proposed_action,
                idempotency_key=build_idempotency_key(approval, analysis.proposed_action),
            )
            audit_events = (
                review_event,
                self._execution_audit(execution, "action.execution_claimed"),
            )

        self.store.record_review(
            approval,
            execution,
            audit_events=audit_events,
        )
        if execution is None:
            return approval, None

        execution = self._begin_execution_attempt(execution)
        try:
            result = self.action_executor.execute(
                execution.action,
                approval=approval,
                idempotency_key=execution.idempotency_key,
            )
        except Exception:
            result = ExecutionResult(
                state=ExecutionState.UNKNOWN,
                message=(
                    "Provider outcome is unknown; reconcile this execution before any "
                    "further action."
                ),
            )
        return approval, self._persist_execution_result(execution, result)

    def get_execution_for_analysis(self, analysis_id: str) -> ActionExecution:
        if self.store.get_analysis(analysis_id) is None:
            raise NotFoundError(f"analysis not found: {analysis_id}")
        execution = self.store.get_execution_for_analysis(analysis_id)
        if execution is None:
            raise NotFoundError(f"execution not found for analysis: {analysis_id}")
        self._verify_execution_integrity(execution)
        self._approved_review_for_execution(execution)
        return execution

    def reconcile_execution(self, execution_id: str) -> ActionExecution:
        execution = self.store.get_execution(execution_id)
        if execution is None:
            raise NotFoundError(f"execution not found: {execution_id}")
        self._verify_execution_integrity(execution)
        self._approved_review_for_execution(execution)
        if execution.state.terminal:
            raise InvalidTransitionError("terminal execution does not require reconciliation")

        execution = self._begin_execution_attempt(execution)
        try:
            result = self.action_executor.reconcile(execution)
        except Exception:
            result = ExecutionResult(
                state=ExecutionState.UNKNOWN,
                message="Reconciliation outcome is unknown; manual investigation is required.",
            )
        return self._persist_execution_result(execution, result)

    def record_outcome(self, outcome: Outcome) -> None:
        if self.store.get_ticket(outcome.ticket_id) is None:
            raise NotFoundError(f"ticket not found: {outcome.ticket_id}")
        self.store.put_outcome(outcome)
        self._audit(
            "outcome.recorded",
            outcome.ticket_id,
            {
                "resolved": outcome.resolved,
                "escalated": outcome.escalated,
                "csat": outcome.csat,
                "model_cost_usd": str(outcome.model_cost_usd),
            },
        )

    def metrics(self) -> dict[str, float | int | str]:
        analyses = self.store.list_analyses()
        outcomes = self.store.list_outcomes()
        executions = self.store.list_executions()
        resolved = sum(item.resolved for item in outcomes)
        total_cost = sum((item.model_cost_usd for item in outcomes), Decimal("0"))
        terminal_executions = [item for item in executions if item.state.terminal]
        reconciliation_required = [
            item
            for item in executions
            if item.state
            in {
                ExecutionState.PENDING,
                ExecutionState.IN_FLIGHT,
                ExecutionState.SUBMITTED,
                ExecutionState.UNKNOWN,
            }
        ]
        return {
            "analyses": len(analyses),
            "outcomes": len(outcomes),
            "resolution_rate": resolved / len(outcomes) if outcomes else 0.0,
            "review_rate": (
                sum(item.disposition is Disposition.REVIEW_REQUIRED for item in analyses)
                / len(analyses)
                if analyses
                else 0.0
            ),
            "evidence_coverage": (
                sum(bool(item.citations) for item in analyses) / len(analyses) if analyses else 0.0
            ),
            "action_success_rate": (
                sum(item.state is ExecutionState.SUCCEEDED for item in terminal_executions)
                / len(terminal_executions)
                if terminal_executions
                else 0.0
            ),
            "action_failure_rate": (
                sum(item.state is ExecutionState.FAILED for item in terminal_executions)
                / len(terminal_executions)
                if terminal_executions
                else 0.0
            ),
            "action_unknown_rate": (
                sum(item.state is ExecutionState.UNKNOWN for item in executions) / len(executions)
                if executions
                else 0.0
            ),
            "actions_requiring_reconciliation": len(reconciliation_required),
            "cost_per_resolved_outcome_usd": (
                str((total_cost / resolved).quantize(Decimal("0.0001"))) if resolved else "0"
            ),
        }

    def evaluate_cases(self, cases: list[EvaluationCase]) -> EvaluationSummary:
        intent_hits = 0
        disposition_hits = 0
        disposition_total = 0
        citation_hits = 0
        citation_total = 0
        unsafe_actions = 0
        for case in cases:
            self.seed_customer(case.customer)
            result = self.analyze(case.ticket)
            intent_hits += result.intent is case.expected_intent
            if case.expected_disposition is not None:
                disposition_total += 1
                disposition_hits += result.disposition is case.expected_disposition
            actual_citations = {item.article_id for item in result.citations}
            citation_hits += len(actual_citations & case.expected_article_ids)
            citation_total += len(case.expected_article_ids)
            if result.disposition is Disposition.RESPOND and result.proposed_action is not None:
                unsafe_actions += 1
        total = len(cases)
        return EvaluationSummary(
            cases=total,
            intent_accuracy=intent_hits / total if total else 0.0,
            disposition_accuracy=(
                disposition_hits / disposition_total if disposition_total else None
            ),
            citation_recall=citation_hits / citation_total if citation_total else 1.0,
            unsafe_action_rate=unsafe_actions / total if total else 0.0,
        )

    def verify_audit(self) -> None:
        verify_chain(self.store.list_audit())
