"""Narrow persistence adapter for exactly-once external webhook audit commits."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from resolveops.adapters.sqlite import SQLiteStore
from resolveops.domain.errors import IntegrityError
from resolveops.domain.models import AuditEvent, AuditEventDraft


class SQLiteWebhookStore(SQLiteStore):
    """SQLiteStore with atomic external-event claim plus audit append semantics."""

    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS external_event_claims (
                    unique_key TEXT PRIMARY KEY,
                    audit_sequence INTEGER UNIQUE NOT NULL,
                    FOREIGN KEY(audit_sequence) REFERENCES audit_events(sequence)
                )
                """
            )
            dangling = connection.execute(
                """
                SELECT c.unique_key
                FROM external_event_claims AS c
                LEFT JOIN audit_events AS a ON a.sequence = c.audit_sequence
                WHERE a.sequence IS NULL
                LIMIT 1
                """
            ).fetchone()
            if dangling is not None:
                raise IntegrityError("external event claim references missing audit evidence")

    def append_audit_event_once(
        self,
        unique_key: str,
        event_type: str,
        entity_id: str,
        payload: dict[str, object],
    ) -> AuditEvent | None:
        if not unique_key:
            raise ValueError("audit event unique key must not be empty")
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT audit_sequence FROM external_event_claims WHERE unique_key=?",
                    (unique_key,),
                ).fetchone()
                if existing is not None:
                    return None
                event = self._append_draft(
                    connection,
                    AuditEventDraft(
                        event_type=event_type,
                        entity_id=entity_id,
                        payload=payload,
                    ),
                )
                connection.execute(
                    "INSERT INTO external_event_claims(unique_key,audit_sequence) VALUES(?,?)",
                    (unique_key, event.sequence),
                )
                return event
        except sqlite3.IntegrityError as exc:
            raise IntegrityError("external event claim could not be persisted atomically") from exc
