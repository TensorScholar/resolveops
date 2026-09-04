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
            rows = connection.execute(
                """
                SELECT c.unique_key,a.payload
                FROM external_event_claims AS c
                LEFT JOIN audit_events AS a ON a.sequence = c.audit_sequence
                ORDER BY c.unique_key
                """
            ).fetchall()
            for unique_key, raw_event in rows:
                if raw_event is None:
                    raise IntegrityError("external event claim references missing audit evidence")
                event = self._decode(raw_event, AuditEvent, label="external event audit")
                identity_hash = event.payload.get("external_event_identity_hash")
                if not isinstance(identity_hash, str) or not identity_hash:
                    raise IntegrityError(
                        f"external event claim lacks identity evidence: {unique_key}"
                    )

    @staticmethod
    def _identity_hash(payload: dict[str, object]) -> str:
        identity_hash = payload.get("external_event_identity_hash")
        if not isinstance(identity_hash, str) or not identity_hash:
            raise ValueError("external event audit payload must contain an identity hash")
        return identity_hash

    def append_audit_event_once(
        self,
        unique_key: str,
        event_type: str,
        entity_id: str,
        payload: dict[str, object],
    ) -> AuditEvent | None:
        if not unique_key:
            raise ValueError("audit event unique key must not be empty")
        incoming_identity_hash = self._identity_hash(payload)
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT a.payload
                    FROM external_event_claims AS c
                    JOIN audit_events AS a ON a.sequence = c.audit_sequence
                    WHERE c.unique_key=?
                    """,
                    (unique_key,),
                ).fetchone()
                if existing is not None:
                    event = self._decode(existing[0], AuditEvent, label="external event audit")
                    existing_identity_hash = event.payload.get("external_event_identity_hash")
                    if (
                        event.event_type != event_type
                        or event.entity_id != entity_id
                        or existing_identity_hash != incoming_identity_hash
                    ):
                        raise IntegrityError(
                            "external event identity was reused for conflicting content"
                        )
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
