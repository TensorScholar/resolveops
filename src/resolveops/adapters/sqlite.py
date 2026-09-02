"""Single-node SQLite persistence."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

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
                CREATE TABLE IF NOT EXISTS execution_claims (
                    analysis_id TEXT PRIMARY KEY,
                    approval_id TEXT UNIQUE NOT NULL,
                    execution_id TEXT UNIQUE NOT NULL
                );
                """
            )
            connection.execute("BEGIN IMMEDIATE")
            self._validate_and_upgrade_execution_claims(connection)

    @staticmethod
    def _decode(payload: str, model_type: type[T], *, label: str) -> T:
        try:
            return model_type.model_validate_json(payload)
        except (ValidationError, ValueError, TypeError) as exc:
            raise IntegrityError(f"invalid persisted {label} payload") from exc

    def _validate_and_upgrade_execution_claims(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        execution_rows = connection.execute(
            "SELECT id,payload FROM objects WHERE kind='execution' ORDER BY id"
        ).fetchall()
        executions: dict[str, ActionExecution] = {}
        for object_id, payload in execution_rows:
            try:
                execution = self._decode(payload, ActionExecution, label="execution")
            except IntegrityError as exc:
                try:
                    raw = json.loads(payload)
                except (json.JSONDecodeError, TypeError):
                    raise
                if isinstance(raw, dict) and "success" in raw and "idempotency_key" not in raw:
                    raise IntegrityError(
                        "legacy execution records use the pre-lifecycle schema; "
                        "automatic migration is unsafe"
                    ) from exc
                raise
            if execution.id != object_id:
                raise IntegrityError("persisted execution object id does not match its key")
            executions[execution.id] = execution

        approval_claim_rows = connection.execute(
            "SELECT analysis_id,approval_id FROM approval_claims ORDER BY analysis_id"
        ).fetchall()
        approvals: dict[str, Approval] = {}
        approval_by_analysis: dict[str, Approval] = {}
        for analysis_id, approval_id in approval_claim_rows:
            row = connection.execute(
                "SELECT payload FROM objects WHERE kind='approval' AND id=?",
                (approval_id,),
            ).fetchone()
            if row is None:
                raise IntegrityError("approval claim references a missing approval")
            approval = self._decode(row[0], Approval, label="approval")
            if approval.id != approval_id or approval.analysis_id != analysis_id:
                raise IntegrityError("approval claim does not match persisted approval")
            approvals[approval.id] = approval
            approval_by_analysis[analysis_id] = approval

        execution_claim_rows = connection.execute(
            """
            SELECT analysis_id,approval_id,execution_id
            FROM execution_claims
            ORDER BY analysis_id
            """
        ).fetchall()
        claims_by_analysis: dict[str, tuple[str, str]] = {}
        claims_by_approval: dict[str, tuple[str, str]] = {}
        claims_by_execution: dict[str, tuple[str, str]] = {}
        for analysis_id, approval_id, execution_id in execution_claim_rows:
            claimed_execution = executions.get(execution_id)
            claimed_approval = approvals.get(approval_id)
            if claimed_execution is None:
                raise IntegrityError("execution claim references a missing execution")
            if claimed_approval is None or claimed_approval.state is not ReviewState.APPROVED:
                raise IntegrityError("execution claim lacks a matching approved review")
            if (
                claimed_execution.analysis_id != analysis_id
                or claimed_execution.approval_id != approval_id
                or claimed_approval.analysis_id != analysis_id
            ):
                raise IntegrityError("execution claim does not match persisted execution")
            claims_by_analysis[analysis_id] = (approval_id, execution_id)
            claims_by_approval[approval_id] = (analysis_id, execution_id)
            claims_by_execution[execution_id] = (analysis_id, approval_id)

        for execution in executions.values():
            execution_approval = approvals.get(execution.approval_id)
            if (
                execution_approval is None
                or execution_approval.analysis_id != execution.analysis_id
                or execution_approval.state is not ReviewState.APPROVED
            ):
                raise IntegrityError("persisted execution lacks its approved review claim")

            existing = claims_by_execution.get(execution.id)
            if existing is not None:
                if existing != (execution.analysis_id, execution.approval_id):
                    raise IntegrityError("execution claim conflicts with persisted execution")
                continue
            if (
                execution.analysis_id in claims_by_analysis
                or execution.approval_id in claims_by_approval
            ):
                raise IntegrityError("execution claim conflicts with persisted review")

            connection.execute(
                """
                INSERT INTO execution_claims(analysis_id,approval_id,execution_id)
                VALUES(?,?,?)
                """,
                (execution.analysis_id, execution.approval_id, execution.id),
            )
            claims_by_analysis[execution.analysis_id] = (
                execution.approval_id,
                execution.id,
            )
            claims_by_approval[execution.approval_id] = (
                execution.analysis_id,
                execution.id,
            )
            claims_by_execution[execution.id] = (
                execution.analysis_id,
                execution.approval_id,
            )

        for analysis_id, approval in approval_by_analysis.items():
            execution_claim = claims_by_analysis.get(analysis_id)
            if approval.state is ReviewState.APPROVED and execution_claim is None:
                raise IntegrityError(
                    "approved legacy review has no persisted execution; "
                    "external side-effect state is ambiguous"
                )
            if approval.state is ReviewState.REJECTED and execution_claim is not None:
                raise IntegrityError("rejected review cannot own an execution claim")

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

    def _append_draft(
        self,
        connection: sqlite3.Connection,
        draft: AuditEventDraft,
    ) -> AuditEvent:
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
            event_type=draft.event_type,
            entity_id=draft.entity_id,
            payload=draft.payload,
            previous_hash=previous_hash,
        )
        connection.execute(
            "INSERT INTO audit_events(sequence,payload) VALUES(?,?)",
            (event.sequence, event.model_dump_json()),
        )
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

    def record_review(
        self,
        approval: Approval,
        execution: ActionExecution | None,
        *,
        audit_events: tuple[AuditEventDraft, ...],
    ) -> tuple[AuditEvent, ...]:
        self._validate_review_transition(approval, execution, audit_events)
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
                if execution is not None:
                    connection.execute(
                        """
                        INSERT INTO execution_claims(analysis_id,approval_id,execution_id)
                        VALUES(?,?,?)
                        """,
                        (execution.analysis_id, execution.approval_id, execution.id),
                    )
                    connection.execute(
                        "INSERT INTO objects(kind,id,payload) VALUES('execution',?,?)",
                        (execution.id, execution.model_dump_json()),
                    )
                return tuple(self._append_draft(connection, draft) for draft in audit_events)
        except sqlite3.IntegrityError as exc:
            raise InvalidTransitionError("analysis has already been reviewed") from exc

    def get_approval(self, approval_id: str) -> Approval | None:
        return self._get("approval", approval_id, Approval)

    def get_execution(self, execution_id: str) -> ActionExecution | None:
        return self._get("execution", execution_id, ActionExecution)

    def get_execution_for_analysis(self, analysis_id: str) -> ActionExecution | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT execution_id FROM execution_claims WHERE analysis_id=?",
                (analysis_id,),
            ).fetchone()
        return self.get_execution(row[0]) if row else None

    def update_execution(
        self,
        execution: ActionExecution,
        *,
        audit_event: AuditEventDraft,
    ) -> AuditEvent:
        if audit_event.entity_id != execution.id:
            raise IntegrityError("execution audit event targets the wrong entity")
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM objects WHERE kind='execution' AND id=?",
                (execution.id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"execution not found: {execution.id}")
            current = self._decode(row[0], ActionExecution, label="execution")
            validate_execution_update(current, execution)
            cursor = connection.execute(
                "UPDATE objects SET payload=? WHERE kind='execution' AND id=?",
                (execution.model_dump_json(), execution.id),
            )
            if cursor.rowcount != 1:
                raise IntegrityError("execution update was not persisted")
            return self._append_draft(connection, audit_event)

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
            return self._append_draft(
                connection,
                AuditEventDraft(
                    event_type=event_type,
                    entity_id=entity_id,
                    payload=payload,
                ),
            )

    def list_audit(self) -> list[AuditEvent]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT payload FROM audit_events ORDER BY sequence"
            ).fetchall()
        return [self._decode(row[0], AuditEvent, label="audit event") for row in rows]
