"""In-memory adapter for tests and demos."""

from __future__ import annotations

from resolveops.domain.models import (
    ActionExecution,
    AnalysisResult,
    Approval,
    AuditEvent,
    CustomerProfile,
    KnowledgeArticle,
    Outcome,
    Ticket,
)


class MemoryStore:
    def __init__(self) -> None:
        self.tickets: dict[str, Ticket] = {}
        self.customers: dict[str, CustomerProfile] = {}
        self.articles: dict[str, KnowledgeArticle] = {}
        self.analyses: dict[str, AnalysisResult] = {}
        self.approvals: dict[str, Approval] = {}
        self.executions: dict[str, ActionExecution] = {}
        self.outcomes: list[Outcome] = []
        self.audit: list[AuditEvent] = []

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

    def put_approval(self, approval: Approval) -> None:
        self.approvals[approval.id] = approval

    def get_approval(self, approval_id: str) -> Approval | None:
        return self.approvals.get(approval_id)

    def put_execution(self, execution: ActionExecution) -> None:
        self.executions[execution.id] = execution

    def list_executions(self) -> list[ActionExecution]:
        return list(self.executions.values())

    def put_outcome(self, outcome: Outcome) -> None:
        self.outcomes.append(outcome)

    def list_outcomes(self) -> list[Outcome]:
        return list(self.outcomes)

    def append_audit(self, event: AuditEvent) -> None:
        self.audit.append(event)

    def list_audit(self) -> list[AuditEvent]:
        return list(self.audit)
