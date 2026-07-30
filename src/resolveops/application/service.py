"""ResolveOps use cases."""

from __future__ import annotations

from decimal import Decimal

from resolveops.domain.audit import make_event, verify_chain
from resolveops.domain.errors import InvalidTransitionError, NotFoundError, PolicyDeniedError
from resolveops.domain.models import (
    ActionExecution,
    AnalysisResult,
    Approval,
    CustomerProfile,
    Disposition,
    EvaluationCase,
    EvaluationSummary,
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
        events = self.store.list_audit()
        previous = events[-1].event_hash if events else "0" * 64
        event = make_event(
            sequence=len(events) + 1,
            event_type=event_type,
            entity_id=entity_id,
            payload=payload,
            previous_hash=previous,
        )
        self.store.append_audit(event)

    def seed_customer(self, customer: CustomerProfile) -> None:
        self.store.put_customer(customer)

    def seed_article(self, article: object) -> None:
        from resolveops.domain.models import KnowledgeArticle

        if not isinstance(article, KnowledgeArticle):
            raise TypeError("article must be KnowledgeArticle")
        self.store.put_article(article)

    def analyze(self, ticket: Ticket) -> AnalysisResult:
        customer = self.store.get_customer(ticket.customer_id)
        if customer is None:
            raise NotFoundError(f"customer not found: {ticket.customer_id}")
        self.store.put_ticket(ticket)
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
        self.store.put_analysis(analysis)
        self._audit(
            "ticket.analyzed",
            analysis.id,
            {
                "ticket_id": ticket.id,
                "intent": intent.value,
                "disposition": analysis.disposition.value,
                "citation_ids": [item.article_id for item in citations],
            },
        )
        return analysis

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
        if analysis.disposition is Disposition.DENY:
            raise PolicyDeniedError("denied analysis cannot be approved")
        if analysis.proposed_action is None:
            raise InvalidTransitionError("analysis has no action to review")
        if analysis.disposition not in {Disposition.REVIEW_REQUIRED, Disposition.ESCALATE}:
            raise InvalidTransitionError("analysis is not waiting for review")
        approval = Approval(
            analysis_id=analysis.id,
            reviewer=reviewer,
            state=ReviewState.APPROVED if approve else ReviewState.REJECTED,
            note=note,
        )
        self.store.put_approval(approval)
        self._audit(
            "analysis.reviewed",
            approval.id,
            {"analysis_id": analysis.id, "state": approval.state.value, "reviewer": reviewer},
        )
        if not approve:
            return approval, None
        success, message, reference = self.action_executor.execute(
            analysis.proposed_action,
            approval=approval,
        )
        execution = ActionExecution(
            analysis_id=analysis.id,
            approval_id=approval.id,
            action=analysis.proposed_action,
            success=success,
            message=message,
            external_reference=reference,
        )
        self.store.put_execution(execution)
        self._audit(
            "action.executed",
            execution.id,
            {
                "analysis_id": analysis.id,
                "success": success,
                "external_reference": reference,
            },
        )
        return approval, execution

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
                sum(item.success for item in executions) / len(executions) if executions else 0.0
            ),
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
