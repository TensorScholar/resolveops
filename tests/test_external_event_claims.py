from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from resolveops.adapters.memory import MemoryStore
from resolveops.adapters.sqlite import SQLiteStore
from resolveops.adapters.webhook_store import SQLiteWebhookStore
from resolveops.domain.errors import IntegrityError

_EVENT_KEY = "stripe:0:evt_claim"
_EVENT_TYPE = "action.outcome_observed"
_ENTITY_ID = "execution_1"


def _payload(identity_hash: str) -> dict[str, object]:
    return {
        "external_event_identity_hash": identity_hash,
        "stripe_event_id": "evt_claim",
    }


def test_memory_claim_is_idempotent_but_rejects_identity_collision() -> None:
    store = MemoryStore()

    first = store.append_audit_event_once(
        _EVENT_KEY,
        "identity-a",
        _EVENT_TYPE,
        _ENTITY_ID,
        _payload("identity-a"),
    )
    duplicate = store.append_audit_event_once(
        _EVENT_KEY,
        "identity-a",
        _EVENT_TYPE,
        _ENTITY_ID,
        _payload("identity-a"),
    )

    assert first is not None
    assert duplicate is None
    with pytest.raises(IntegrityError, match="reused for conflicting content"):
        store.append_audit_event_once(
            _EVENT_KEY,
            "identity-b",
            _EVENT_TYPE,
            _ENTITY_ID,
            _payload("identity-b"),
        )
    assert len(store.list_audit()) == 1


def test_sqlite_claim_survives_restart_and_rejects_identity_collision(tmp_path) -> None:
    path = tmp_path / "event-claims.db"
    store = SQLiteWebhookStore(path)
    first = store.append_audit_event_once(
        _EVENT_KEY,
        "identity-a",
        _EVENT_TYPE,
        _ENTITY_ID,
        _payload("identity-a"),
    )
    assert first is not None

    restarted = SQLiteWebhookStore(path)
    assert (
        restarted.append_audit_event_once(
            _EVENT_KEY,
            "identity-a",
            _EVENT_TYPE,
            _ENTITY_ID,
            _payload("identity-a"),
        )
        is None
    )
    with pytest.raises(IntegrityError, match="reused for conflicting content"):
        restarted.append_audit_event_once(
            _EVENT_KEY,
            "identity-b",
            _EVENT_TYPE,
            _ENTITY_ID,
            _payload("identity-b"),
        )
    assert len(restarted.list_audit()) == 1


def test_concurrent_sqlite_identity_collision_commits_exactly_one_fact(tmp_path) -> None:
    path = tmp_path / "event-collision.db"
    SQLiteWebhookStore(path)

    def claim(identity_hash: str) -> object:
        return SQLiteWebhookStore(path).append_audit_event_once(
            _EVENT_KEY,
            identity_hash,
            _EVENT_TYPE,
            _ENTITY_ID,
            _payload(identity_hash),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim, identity) for identity in ("identity-a", "identity-b")]

    committed = 0
    conflicts = 0
    for future in futures:
        try:
            if future.result() is not None:
                committed += 1
        except IntegrityError as exc:
            assert "reused for conflicting content" in str(exc)
            conflicts += 1

    assert committed == 1
    assert conflicts == 1
    events = SQLiteWebhookStore(path).list_audit()
    assert len(events) == 1
    assert events[0].payload["external_event_identity_hash"] in {"identity-a", "identity-b"}


def test_legacy_sqlite_claim_backfills_only_from_bound_audit_evidence(tmp_path) -> None:
    path = tmp_path / "legacy-event-claims.db"
    base = SQLiteStore(path)
    event = base.append_audit_event(
        _EVENT_TYPE,
        _ENTITY_ID,
        _payload("identity-a"),
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE external_event_claims (
                unique_key TEXT PRIMARY KEY,
                audit_sequence INTEGER UNIQUE NOT NULL,
                FOREIGN KEY(audit_sequence) REFERENCES audit_events(sequence)
            )
            """
        )
        connection.execute(
            "INSERT INTO external_event_claims(unique_key,audit_sequence) VALUES(?,?)",
            (_EVENT_KEY, event.sequence),
        )

    upgraded = SQLiteWebhookStore(path)

    assert (
        upgraded.append_audit_event_once(
            _EVENT_KEY,
            "identity-a",
            _EVENT_TYPE,
            _ENTITY_ID,
            _payload("identity-a"),
        )
        is None
    )


def test_legacy_sqlite_claim_without_identity_evidence_fails_closed(tmp_path) -> None:
    path = tmp_path / "ambiguous-event-claims.db"
    base = SQLiteStore(path)
    event = base.append_audit_event(_EVENT_TYPE, _ENTITY_ID, {"stripe_event_id": "evt_claim"})
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE external_event_claims (
                unique_key TEXT PRIMARY KEY,
                audit_sequence INTEGER UNIQUE NOT NULL,
                FOREIGN KEY(audit_sequence) REFERENCES audit_events(sequence)
            )
            """
        )
        connection.execute(
            "INSERT INTO external_event_claims(unique_key,audit_sequence) VALUES(?,?)",
            (_EVENT_KEY, event.sequence),
        )

    with pytest.raises(IntegrityError, match="cannot be upgraded without identity evidence"):
        SQLiteWebhookStore(path)
