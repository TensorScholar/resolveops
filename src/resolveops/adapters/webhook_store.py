"""Narrow persistence adapter for exactly-once external webhook audit commits."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from resolveops.adapters.sqlite import SQLiteStore
from resolveops.domain.errors import IntegrityError
from resolveops.domain.models import AuditEvent, AuditEventDraft


class SQLiteWebhookStore(SQLiteStore):
    """SQLiteStore with atomic external-event identity claim plus audit append semantics."""

    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS external_event_claims (
                    unique_key TEXT PRIMARY KEY,
                    identity_hash TEXT NOT NULL,
                    audit_sequence INTEGER UNIQUE NOT NULL,
                    FOREIGN KEY(audit_sequence) REFERENCES audit_events(sequence)
                )
                """
            )
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(external_event_claims)").fetchall()
            }
            if "identity_hash" not in columns:
                connection.execute(
                    "ALTER TABLE external_event_claims ADD COLUMN identity_hash TEXT"
                )
                legacy_rows = connection.execute(
                    "SELECT unique_key,audit_sequence FROM external_event_claims ORDER BY unique_key"
                ).fetchall()
                for unique_key, audit_sequence in legacy_rows:
                    raw_event = connection.execute(
                        "SELECT payload FROM audit_events WHERE sequence=?",
                        (audit_sequence,),
                    ).fetchone()
                    if raw_event is None:
                        raise IntegrityError(
                            "external event claim references missing audit evidence"
                        )
                    event = self._decode(raw_event[0], AuditEvent, label="external event audit")
                    identity_hash = event.payload.get("external_event_identity_hash")
                    if not isinstance(identity_hash, str) or not identity_hash:
                        raise IntegrityError(
                            "legacy external event claim cannot be upgraded without identity evidence"
                        )
                    connection.execute(
                        "UPDATE external_event_claims SET identity_hash=? WHERE unique_key=?",
                        (identity_hash, unique_key),
                    )

            rows = connection.execute(
                """
                SELECT c.unique_key,c.identity_hash,a.payload
                FROM external_event_claims AS c
                LEFT JOIN audit_events AS a ON a.sequence = c.audit_sequence
                ORDER BY c.unique_key
                """
            ).fetchall()
            for unique_key, identity_hash, raw_event in rows:
                if raw_event is None:
                    raise IntegrityError("external event claim references missing audit evidence")
                if not isinstance(identity_hash, str) or not identity_hash:
                    raise IntegrityError(
                        f"external event claim lacks identity evidence: {unique_key}"
                    )
                event = self._decode(raw_event, AuditEvent, label="external event audit")
                if event.payload.get("external_event_identity_hash") != identity_hash:
                    raise IntegrityError(
                        "external event claim identity does not match its audit evidence"
                    )

    def append_audit_event_once(
        self,
        unique_key: str,
        identity_hash: str,
        event_type: str,
        entity_id: str,
        payload: dict[str, object],
    ) -> AuditEvent | None:
        if not unique_key:
            raise ValueError("audit event unique key must not be empty")
        if not identity_hash:
            raise ValueError("audit event identity hash must not be empty")
        if payload.get("external_event_identity_hash") != identity_hash:
            raise IntegrityError("external event claim does not match its audit payload")
        try:
            with closing(self._connect()) as connection, connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT c.identity_hash,a.payload
                    FROM external_event_claims AS c
                    JOIN audit_events AS a ON a.sequence = c.audit_sequence
                    WHERE c.unique_key=?
                    """,
                    (unique_key,),
                ).fetchone()
                if existing is not None:
                    existing_identity_hash, raw_event = existing
                    event = self._decode(raw_event, AuditEvent, label="external event audit")
                    if (
                        event.event_type != event_type
                        or event.entity_id != entity_id
                        or existing_identity_hash != identity_hash
                        or event.payload.get("external_event_identity_hash") != identity_hash
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
                    """
                    INSERT INTO external_event_claims(unique_key,identity_hash,audit_sequence)
                    VALUES(?,?,?)
                    """,
                    (unique_key, identity_hash, event.sequence),
                )
                return event
        except sqlite3.IntegrityError as exc:
            raise IntegrityError("external event claim could not be persisted atomically") from exc
