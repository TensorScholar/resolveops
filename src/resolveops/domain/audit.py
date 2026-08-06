"""Tamper-evident, append-only audit primitives."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Iterable

from resolveops.domain.errors import IntegrityError
from resolveops.domain.models import AuditEvent


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def object_digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def event_digest(
    *,
    sequence: int,
    event_type: str,
    entity_id: str,
    payload: dict[str, object],
    occurred_at: datetime,
    previous_hash: str,
) -> str:
    body = {
        "sequence": sequence,
        "event_type": event_type,
        "entity_id": entity_id,
        "payload": payload,
        "occurred_at": occurred_at.astimezone(UTC).isoformat(),
        "previous_hash": previous_hash,
    }
    return object_digest(body)


def make_event(
    *,
    sequence: int,
    event_type: str,
    entity_id: str,
    payload: dict[str, object],
    previous_hash: str,
    occurred_at: datetime | None = None,
) -> AuditEvent:
    timestamp = occurred_at or datetime.now(UTC)
    digest = event_digest(
        sequence=sequence,
        event_type=event_type,
        entity_id=entity_id,
        payload=payload,
        occurred_at=timestamp,
        previous_hash=previous_hash,
    )
    return AuditEvent(
        sequence=sequence,
        event_type=event_type,
        entity_id=entity_id,
        payload=payload,
        occurred_at=timestamp,
        previous_hash=previous_hash,
        event_hash=digest,
    )


def verify_chain(events: Iterable[AuditEvent]) -> None:
    previous = "0" * 64
    expected_sequence = 1
    for event in events:
        if event.sequence != expected_sequence or event.previous_hash != previous:
            raise IntegrityError("audit chain sequence or previous hash mismatch")
        expected_hash = event_digest(
            sequence=event.sequence,
            event_type=event.event_type,
            entity_id=event.entity_id,
            payload=event.payload,
            occurred_at=event.occurred_at,
            previous_hash=event.previous_hash,
        )
        if expected_hash != event.event_hash:
            raise IntegrityError("audit event hash mismatch")
        previous = event.event_hash
        expected_sequence += 1
