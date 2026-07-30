"""Single-node SQLite persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

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

T = TypeVar("T", bound=BaseModel)


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS objects (
                    kind TEXT NOT NULL,
                    id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (kind, id)
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                """
            )

    def _put(self, kind: str, identifier: str, model: BaseModel) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO objects(kind,id,payload) VALUES(?,?,?)",
                (kind, identifier, model.model_dump_json()),
            )

    def _get(self, kind: str, identifier: str, model_type: type[T]) -> T | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM objects WHERE kind=? AND id=?", (kind, identifier)
            ).fetchone()
        return model_type.model_validate_json(row[0]) if row else None

    def _list(self, kind: str, model_type: type[T]) -> list[T]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM objects WHERE kind=? ORDER BY id", (kind,)
            ).fetchall()
        return [model_type.model_validate_json(row[0]) for row in rows]

    def put_ticket(self, ticket: Ticket) -> None:
        self._put("ticket", ticket.id, ticket)

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        return self._get("ticket", ticket_id, Ticket)

    def put_customer(self, customer: CustomerProfile) -> None:
        self._put("customer", customer.id, customer)

    def get_customer(self, customer_id: str) -> CustomerProfile | None:
        return self._get("customer", customer_id, CustomerProfile)

    def put_article(self, article: KnowledgeArticle) -> None:
        self._put("article", article.id, article)

    def list_articles(self) -> list[KnowledgeArticle]:
        return self._list("article", KnowledgeArticle)

    def put_analysis(self, analysis: AnalysisResult) -> None:
        self._put("analysis", analysis.id, analysis)

    def get_analysis(self, analysis_id: str) -> AnalysisResult | None:
        return self._get("analysis", analysis_id, AnalysisResult)

    def list_analyses(self) -> list[AnalysisResult]:
        return self._list("analysis", AnalysisResult)

    def put_approval(self, approval: Approval) -> None:
        self._put("approval", approval.id, approval)

    def get_approval(self, approval_id: str) -> Approval | None:
        return self._get("approval", approval_id, Approval)

    def put_execution(self, execution: ActionExecution) -> None:
        self._put("execution", execution.id, execution)

    def list_executions(self) -> list[ActionExecution]:
        return self._list("execution", ActionExecution)

    def put_outcome(self, outcome: Outcome) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO outcomes(payload) VALUES(?)",
                (outcome.model_dump_json(),),
            )

    def list_outcomes(self) -> list[Outcome]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM outcomes ORDER BY id").fetchall()
        return [Outcome.model_validate_json(row[0]) for row in rows]

    def append_audit(self, event: AuditEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_events(sequence,payload) VALUES(?,?)",
                (event.sequence, event.model_dump_json()),
            )

    def list_audit(self) -> list[AuditEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM audit_events ORDER BY sequence"
            ).fetchall()
        return [AuditEvent.model_validate_json(row[0]) for row in rows]
