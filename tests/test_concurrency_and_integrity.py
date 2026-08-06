from __future__ import annotations

import sqlite3
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor

import pytest

from resolveops.adapters.actions import MockActionExecutor
from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.sqlite import SQLiteStore
from resolveops.application.service import ResolveOpsService
from resolveops.domain.errors import IntegrityError, InvalidTransitionError
from resolveops.domain.models import CustomerProfile, KnowledgeArticle, Ticket


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


def test_concurrent_sqlite_audit_appends_are_serialized(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "audit.db")
    service = build_service(store)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(
            executor.map(
                lambda number: service._audit(
                    "test.concurrent", str(number), {"number": number}
                ),
                range(40),
            )
        )

    service.verify_audit()
    events = store.list_audit()
    assert len(events) == 40
    assert [event.sequence for event in events] == list(range(1, 41))


def test_concurrent_review_allows_one_execution(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "review.db")
    service = build_service(store)
    analysis = service.analyze(Ticket(customer_id="c", message="Refund $10"))

    def review(reviewer: str) -> str:
        try:
            service.review(analysis.id, reviewer=reviewer, approve=True)
        except InvalidTransitionError:
            return "rejected"
        return "executed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(review, ["one", "two"]))

    assert sorted(outcomes) == ["executed", "rejected"]
    assert len(store.list_executions()) == 1
    service.verify_audit()


def test_malformed_persisted_json_fails_closed(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "corrupt.db")
    store.put_customer(CustomerProfile(id="c"))
    with closing(sqlite3.connect(store.path)) as connection, connection:
        connection.execute(
            "UPDATE objects SET payload='not-json' WHERE kind='customer' AND id='c'"
        )

    with pytest.raises(IntegrityError, match="invalid persisted customer payload"):
        store.get_customer("c")
