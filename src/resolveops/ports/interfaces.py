"""Application ports."""

from __future__ import annotations

from typing import Protocol

from resolveops.domain.models import (
    ActionExecution,
    ActionProposal,
    AnalysisResult,
    Approval,
    AuditEvent,
    AuditEventDraft,
    CustomerProfile,
    ExecutionResult,
    KnowledgeArticle,
    Outcome,
    PaymentSnapshot,
    Ticket,
)
from resolveops.domain.outcomes import ActionOutcomeResult


class Store(Protocol):
    def get_ticket(self, ticket_id: str) -> Ticket | None: ...
    def put_customer(self, customer: CustomerProfile) -> None: ...
    def get_customer(self, customer_id: str) -> CustomerProfile | None: ...
    def put_article(self, article: KnowledgeArticle) -> None: ...
    def list_articles(self) -> list[KnowledgeArticle]: ...
    def record_analysis(
        self,
        ticket: Ticket,
        analysis: AnalysisResult,
        *,
        audit_event: AuditEventDraft,
    ) -> AnalysisResult: ...
    def get_analysis(self, analysis_id: str) -> AnalysisResult | None: ...
    def get_analysis_for_ticket(self, ticket_id: str) -> AnalysisResult | None: ...
    def list_analyses(self) -> list[AnalysisResult]: ...
    def record_review(
        self,
        approval: Approval,
        execution: ActionExecution | None,
        *,
        audit_events: tuple[AuditEventDraft, ...],
    ) -> tuple[AuditEvent, ...]: ...
    def get_approval(self, approval_id: str) -> Approval | None: ...
    def get_execution(self, execution_id: str) -> ActionExecution | None: ...
    def get_execution_for_analysis(self, analysis_id: str) -> ActionExecution | None: ...
    def update_execution(
        self,
        execution: ActionExecution,
        *,
        audit_event: AuditEventDraft,
    ) -> AuditEvent: ...
    def list_executions(self) -> list[ActionExecution]: ...
    def put_outcome(self, outcome: Outcome) -> None: ...
    def list_outcomes(self) -> list[Outcome]: ...
    def append_audit(self, event: AuditEvent) -> None: ...
    def append_audit_event(
        self, event_type: str, entity_id: str, payload: dict[str, object]
    ) -> AuditEvent: ...
    def list_audit(self) -> list[AuditEvent]: ...


class BillingReader(Protocol):
    def get_payment(self, payment_id: str) -> PaymentSnapshot | None: ...


class ResponseGenerator(Protocol):
    def generate(
        self,
        *,
        ticket: Ticket,
        customer: CustomerProfile,
        citations: tuple[object, ...],
        intent: str,
    ) -> tuple[str, str, float]: ...


class ActionExecutor(Protocol):
    def execute(
        self,
        action: ActionProposal,
        *,
        approval: Approval,
        idempotency_key: str,
    ) -> ExecutionResult: ...

    def reconcile(self, execution: ActionExecution) -> ExecutionResult: ...


class ActionOutcomeVerifier(Protocol):
    """Read the current external/customer outcome for an already-identified operation."""

    def verify(self, execution: ActionExecution) -> ActionOutcomeResult: ...
