"""Single-node SQLite persistence."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from resolveops.domain.audit import make_event
from resolveops.domain.errors import IntegrityError, InvalidTransitionError
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
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
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
                CREATE TABLE IF NOT EXISTS approval_claims (
                    analysis_id TEXT PRIMARY KEY,
                    approval_id TEXT UNIQUE NOT NULL
                );
                """
            )

    @staticmethod
    def _decode(payload: str, model_type: type[T], *, label: str) -> T:
        try:
            return model_type.model_validate_json(payload)
        except (ValidationError, ValueError, TypeError) as exc:
            raise IntegrityError(f"invalid persisted {label} payload") from exc

    def _put(self, kind: str, identifier: str, model: BaseModel) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT OR REPLACE INTO objects(kind,id,payload) VALUES(?,?,?)",
                (kind, identifier, model.model_dump_json()),
            )

    def _get(self, kind: str, identifier: str, model_type: type[T]) -> T | None:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT payload FROM objects WHERE kind=? AND id=?", (kind, identifier)
            ).fetchone()
        return self._decode(row[0], model_type, label=kind) if row else None

    def _list(self, kind: str, model_type: type[T]) -> list[T]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT payload FROM objects WHERE kind=? ORDER BY id", (kind,)
            ).fetchall()
        return [self._decode(row[0], model_type, label=kind) for row in rows]

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
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO approval_claims(analysis_id,approval_id) VALUES(?,?)",
                    (approval.analysis_id, approval.id),
                )
                connection.execute(
                    "INSERT INTO objects(kind,id,payload) VALUES('approval',?,?)",
                    (approval.id, approval.model_dump_json()),
                )
        except sqlite3.IntegrityError as exc:
            raise InvalidTransitionError("analysis has already been reviewed") from exc

    def get_approval(self, approval_id: str) -> Approval | None:
        return self._get("approval", approval_id, Approval)

    def put_execution(self, execution: ActionExecution) -> None:
        self._put("execution", execution.id, execution)

    def list_executions(self) -> list[ActionExecution]:
        return self._list("execution", ActionExecution)

    def put_outcome(self, outcome: Outcome) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO outcomes(payload) VALUES(?)",
                (outcome.model_dump_json(),),
            )

    def list_outcomes(self) -> list[Outcome]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute("SELECT payload FROM outcomes ORDER BY id").fetchall()
        return [self._decode(row[0], Outcome, label="outcome") for row in rows]

    def append_audit(self, event: AuditEvent) -> None:
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    "INSERT INTO audit_events(sequence,payload) VALUES(?,?)",
                    (event.sequence, event.model_dump_json()),
                )
        except sqlite3.IntegrityError as exc:
            raise IntegrityError("audit sequence must be append-only") from exc

    def append_audit_event(
        self, event_type: str, entity_id: str, payload: dict[str, object]
    ) -> AuditEvent:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM audit_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if row:
                latest = self._decode(row[0], AuditEvent, label="audit event")
                sequence = latest.sequence + 1
                previous_hash = latest.event_hash
            else:
                sequence = 1
                previous_hash = "0" * 64
            event = make_event(
                sequence=sequence,
                event_type=event_type,
                entity_id=entity_id,
                payload=payload,
                previous_hash=previous_hash,
            )
            connection.execute(
                "INSERT INTO audit_events(sequence,payload) VALUES(?,?)",
                (event.sequence, event.model_dump_json()),
            )
            return event

    def list_audit(self) -> list[AuditEvent]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT payload FROM audit_events ORDER BY sequence"
            ).fetchall()
        return [self._decode(row[0], AuditEvent, label="audit event") for row in rows]
