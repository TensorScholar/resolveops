"""In-memory adapter for tests and demos."""

from __future__ import annotations

from threading import RLock

from resolveops.domain.audit import make_event
from resolveops.domain.errors import IntegrityError, InvalidTransitionError, NotFoundError
from resolveops.domain.execution import validate_execution_update
from resolveops.domain.models import (
    ActionExecution,
    AnalysisResult,
    Approval,
    AuditEvent,
    AuditEventDraft,
    CustomerProfile,
    KnowledgeArticle,
    Outcome,
    ReviewState,
    Ticket,
)


class MemoryStore:
    def __init__(self) -> None:
        self.tickets: dict[str, Ticket] = {}
        self.customers: dict[str, CustomerProfile] = {}
        self.articles: dict[str, KnowledgeArticle] = {}
        self.analyses: dict[str, AnalysisResult] = {}
        self.approvals: dict[str, Approval] = {}
        self._approval_by_analysis: dict[str, str] = {}
        self.executions: dict[str, ActionExecution] = {}
        self._execution_by_approval: dict[str, str] = {}
        self._execution_by_analysis: dict[str, str] = {}
        self.outcomes: list[Outcome] = []
        self.audit: list[AuditEvent] = []
        self._lock = RLock()

    def put_ticket(self, ticket: Ticket) -> None:
        self.tickets[ticket.id] = ticket

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        return self.tickets.get(ticket_id)

    def put_customer(self, customer: CustomerProfile) -> None:
        self.customers[customer.id] = customer

    def get_customer(self, customer_id: str) -> CustomerProfile | None:
        return self.customers.get(customer_id)

    def put_article(self, article: KnowledgeArticle) -> None:
        self.articles[article.id] = article

    def list_articles(self) -> list[KnowledgeArticle]:
        return list(self.articles.values())

    def put_analysis(self, analysis: AnalysisResult) -> None:
        self.analyses[analysis.id] = analysis

    def get_analysis(self, analysis_id: str) -> AnalysisResult | None:
        return self.analyses.get(analysis_id)

    def list_analyses(self) -> list[AnalysisResult]:
        return list(self.analyses.values())

    def _append_draft_locked(self, draft: AuditEventDraft) -> AuditEvent:
        previous = self.audit[-1].event_hash if self.audit else "0" * 64
        event = make_event(
            sequence=len(self.audit) + 1,
            event_type=draft.event_type,
            entity_id=draft.entity_id,
            payload=draft.payload,
            previous_hash=previous,
        )
        self.audit.append(event)
        return event

    @staticmethod
    def _validate_review_transition(
        approval: Approval,
        execution: ActionExecution | None,
        audit_events: tuple[AuditEventDraft, ...],
    ) -> None:
        expected_events = 2 if execution is not None else 1
        if len(audit_events) != expected_events:
            raise IntegrityError("review transition has inconsistent audit evidence")
        if execution is None:
            if approval.state is ReviewState.APPROVED:
                raise IntegrityError("approved action review must claim an execution")
            return
        if approval.state is not ReviewState.APPROVED:
            raise IntegrityError("rejected review cannot claim an execution")
        if (
            execution.approval_id != approval.id
            or execution.analysis_id != approval.analysis_id
            or execution.attempt_count != 0
        ):
            raise IntegrityError("execution claim does not match approved review")

    def record_review(
        self,
        approval: Approval,
        execution: ActionExecution | None,
        *,
        audit_events: tuple[AuditEventDraft, ...],
    ) -> tuple[AuditEvent, ...]:
        self._validate_review_transition(approval, execution, audit_events)
        with self._lock:
            if approval.analysis_id in self._approval_by_analysis:
                raise InvalidTransitionError("analysis has already been reviewed")
            self.approvals[approval.id] = approval
            self._approval_by_analysis[approval.analysis_id] = approval.id
            if execution is not None:
                if (
                    execution.approval_id in self._execution_by_approval
                    or execution.analysis_id in self._execution_by_analysis
                ):
                    raise InvalidTransitionError("approved action already has an execution")
                self.executions[execution.id] = execution
                self._execution_by_approval[execution.approval_id] = execution.id
                self._execution_by_analysis[execution.analysis_id] = execution.id
            return tuple(self._append_draft_locked(draft) for draft in audit_events)

    def get_approval(self, approval_id: str) -> Approval | None:
        return self.approvals.get(approval_id)

    def get_execution(self, execution_id: str) -> ActionExecution | None:
        return self.executions.get(execution_id)

    def get_execution_for_analysis(self, analysis_id: str) -> ActionExecution | None:
        execution_id = self._execution_by_analysis.get(analysis_id)
        return self.executions.get(execution_id) if execution_id else None

    def update_execution(
        self,
        execution: ActionExecution,
        *,
        audit_event: AuditEventDraft,
    ) -> AuditEvent:
        with self._lock:
            current = self.executions.get(execution.id)
            if current is None:
                raise NotFoundError(f"execution not found: {execution.id}")
            validate_execution_update(current, execution)
            if audit_event.entity_id != execution.id:
                raise IntegrityError("execution audit event targets the wrong entity")
            self.executions[execution.id] = execution
            return self._append_draft_locked(audit_event)

    def list_executions(self) -> list[ActionExecution]:
        return list(self.executions.values())

    def put_outcome(self, outcome: Outcome) -> None:
        self.outcomes.append(outcome)

    def list_outcomes(self) -> list[Outcome]:
        return list(self.outcomes)

    def append_audit(self, event: AuditEvent) -> None:
        with self._lock:
            if self.audit and event.sequence <= self.audit[-1].sequence:
                raise IntegrityError("audit sequence must be append-only")
            self.audit.append(event)

    def append_audit_event(
        self, event_type: str, entity_id: str, payload: dict[str, object]
    ) -> AuditEvent:
        with self._lock:
            return self._append_draft_locked(
                AuditEventDraft(
                    event_type=event_type,
                    entity_id=entity_id,
                    payload=payload,
                )
            )

    def list_audit(self) -> list[AuditEvent]:
        with self._lock:
            return list(self.audit)
