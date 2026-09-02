from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from resolveops.adapters.actions import MockActionExecutor
from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.sqlite import SQLiteStore
from resolveops.application.service import ResolveOpsService
from resolveops.domain.audit import make_event, object_digest
from resolveops.domain.errors import IntegrityError, InvalidTransitionError
from resolveops.domain.models import (
    AnalysisResult,
    CustomerProfile,
    Disposition,
    IntentKind,
    KnowledgeArticle,
    Ticket,
)


def build_service(store: SQLiteStore) -> ResolveOpsService:
    service = ResolveOpsService(
        store=store,
        generator=DeterministicResponseGenerator(),
        action_executor=MockActionExecutor(),
    )
    service.seed_customer(CustomerProfile(id="c"))
    service.seed_article(
        KnowledgeArticle(
            id="k",
            title="Refund policy",
            body="Refunds require approval.",
            source_uri="kb://k",
            owner="support",
        )
    )
    return service


def stable_ticket() -> Ticket:
    return Ticket(
        id="case-1",
        customer_id="c",
        message="Refund $10",
        received_at=datetime(2026, 9, 2, 18, 0, tzinfo=UTC),
    )


def test_replayed_ticket_returns_one_canonical_analysis(service) -> None:
    ticket = Ticket(
        id="case-memory",
        customer_id="cust_1",
        message="Refund $49",
        received_at=datetime(2026, 9, 2, 18, 0, tzinfo=UTC),
    )

    first = service.analyze(ticket)
    second = service.analyze(Ticket.model_validate(ticket.model_dump()))

    assert second == first
    assert service.store.list_analyses() == [first]
    analyzed_events = [
        event for event in service.store.list_audit() if event.event_type == "ticket.analyzed"
    ]
    assert len(analyzed_events) == 1


def test_same_ticket_id_with_different_content_fails_closed(service) -> None:
    ticket = Ticket(
        id="case-conflict",
        customer_id="cust_1",
        message="Refund $49",
        received_at=datetime(2026, 9, 2, 18, 0, tzinfo=UTC),
    )
    first = service.analyze(ticket)
    conflicting = ticket.model_copy(update={"message": "Refund $149"})

    with pytest.raises(IntegrityError, match="different content"):
        service.analyze(conflicting)

    assert service.store.get_analysis_for_ticket(ticket.id) == first
    assert service.store.get_ticket(ticket.id) == ticket
    assert service.store.list_analyses() == [first]


def test_concurrent_sqlite_ingestion_converges_to_one_analysis(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "concurrent-analysis.db")
    service = build_service(store)
    ticket = stable_ticket()

    with ThreadPoolExecutor(max_workers=4) as executor:
        analyses = list(executor.map(lambda _: service.analyze(ticket), range(4)))

    assert len({analysis.id for analysis in analyses}) == 1
    assert len(store.list_analyses()) == 1
    assert store.get_analysis_for_ticket(ticket.id) == analyses[0]
    analyzed_events = [
        event for event in store.list_audit() if event.event_type == "ticket.analyzed"
    ]
    assert len(analyzed_events) == 1
    service.verify_audit()


def test_sqlite_restart_preserves_canonical_analysis(tmp_path) -> None:
    path = tmp_path / "restart-analysis.db"
    first_service = build_service(SQLiteStore(path))
    ticket = stable_ticket()
    first = first_service.analyze(ticket)

    second_store = SQLiteStore(path)
    second_service = build_service(second_store)
    replayed = second_service.analyze(Ticket.model_validate(ticket.model_dump()))

    assert replayed == first
    assert second_store.list_analyses() == [first]
    assert len(
        [event for event in second_store.list_audit() if event.event_type == "ticket.analyzed"]
    ) == 1


def test_reingestion_after_execution_cannot_create_second_transaction(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "executed-replay.db")
    service = build_service(store)
    ticket = stable_ticket()
    analysis = service.analyze(ticket)
    service.review(analysis.id, reviewer="manager@example.com", approve=True)

    replayed = service.analyze(Ticket.model_validate(ticket.model_dump()))

    assert replayed == analysis
    with pytest.raises(InvalidTransitionError, match="already been reviewed"):
        service.review(replayed.id, reviewer="other@example.com", approve=True)
    assert len(store.list_executions()) == 1


def _create_pre_claim_schema(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE objects (
                kind TEXT NOT NULL,
                id TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (kind, id)
            );
            CREATE TABLE audit_events (
                sequence INTEGER PRIMARY KEY,
                payload TEXT NOT NULL
            );
            """
        )


def _legacy_analysis(ticket: Ticket, analysis_id: str) -> AnalysisResult:
    return AnalysisResult(
        id=analysis_id,
        ticket_id=ticket.id,
        intent=IntentKind.REFUND,
        summary="Legacy analysis",
        draft_reply="Legacy draft",
        confidence=0.9,
        disposition=Disposition.REVIEW_REQUIRED,
    )


def test_upgrade_backfills_one_audited_legacy_analysis_claim(tmp_path) -> None:
    path = tmp_path / "legacy-analysis.db"
    _create_pre_claim_schema(path)
    ticket = stable_ticket()
    analysis = _legacy_analysis(ticket, "ana-legacy")
    event = make_event(
        sequence=1,
        event_type="ticket.analyzed",
        entity_id=analysis.id,
        payload={
            "ticket_id": ticket.id,
            "analysis_hash": object_digest(analysis.model_dump(mode="json")),
        },
        previous_hash="0" * 64,
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO objects(kind,id,payload) VALUES('ticket',?,?)",
            (ticket.id, ticket.model_dump_json()),
        )
        connection.execute(
            "INSERT INTO objects(kind,id,payload) VALUES('analysis',?,?)",
            (analysis.id, analysis.model_dump_json()),
        )
        connection.execute(
            "INSERT INTO audit_events(sequence,payload) VALUES(?,?)",
            (event.sequence, event.model_dump_json()),
        )

    store = SQLiteStore(path)

    assert store.get_analysis_for_ticket(ticket.id) == analysis


def test_upgrade_rejects_multiple_legacy_analyses_for_one_ticket(tmp_path) -> None:
    path = tmp_path / "ambiguous-analysis.db"
    _create_pre_claim_schema(path)
    ticket = stable_ticket()
    first = _legacy_analysis(ticket, "ana-one")
    second = _legacy_analysis(ticket, "ana-two")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO objects(kind,id,payload) VALUES('ticket',?,?)",
            (ticket.id, ticket.model_dump_json()),
        )
        for analysis in (first, second):
            connection.execute(
                "INSERT INTO objects(kind,id,payload) VALUES('analysis',?,?)",
                (analysis.id, analysis.model_dump_json()),
            )

    with pytest.raises(IntegrityError, match="canonical analysis is ambiguous"):
        SQLiteStore(path)
