from datetime import UTC, datetime
from decimal import Decimal

from resolveops.adapters.sqlite import SQLiteStore
from resolveops.domain.audit import make_event
from resolveops.domain.models import (
    ActionExecution,
    ActionKind,
    ActionProposal,
    AnalysisResult,
    Approval,
    AuditEventDraft,
    CustomerProfile,
    Disposition,
    IntentKind,
    KnowledgeArticle,
    ReviewState,
    Ticket,
)


def test_all_sqlite_object_types(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "full.db")
    customer = CustomerProfile(id="c", lifetime_value=Decimal("1"))
    ticket = Ticket(id="t", customer_id="c", message="refund $1")
    article = KnowledgeArticle(
        id="k",
        title="K",
        body="refund",
        source_uri="kb://k",
        owner="o",
    )
    analysis = AnalysisResult(
        id="a",
        ticket_id="t",
        intent=IntentKind.REFUND,
        summary="s",
        draft_reply="d",
        confidence=0.8,
        disposition=Disposition.REVIEW_REQUIRED,
        proposed_action=ActionProposal(
            kind=ActionKind.REFUND,
            resource_id="c",
            amount=Decimal("1"),
            reason="r",
        ),
    )
    approval = Approval(
        id="p",
        analysis_id="a",
        reviewer="r",
        state=ReviewState.APPROVED,
    )
    execution = ActionExecution(
        id="e",
        analysis_id="a",
        approval_id="p",
        action=analysis.proposed_action,
        idempotency_key="ro_sqlite_full",
    )
    event = make_event(
        sequence=1,
        event_type="x",
        entity_id="x",
        payload={"x": 1},
        previous_hash="0" * 64,
        occurred_at=datetime.now(UTC),
    )
    store.put_customer(customer)
    store.put_ticket(ticket)
    store.put_article(article)
    store.put_analysis(analysis)
    store.append_audit(event)
    review_events = store.record_review(
        approval,
        execution,
        audit_events=(
            AuditEventDraft(
                event_type="analysis.reviewed",
                entity_id=approval.id,
                payload={"analysis_id": analysis.id},
            ),
            AuditEventDraft(
                event_type="action.execution_claimed",
                entity_id=execution.id,
                payload={"analysis_id": analysis.id},
            ),
        ),
    )

    assert store.get_analysis("a") == analysis
    assert store.list_analyses() == [analysis]
    assert store.get_approval("p") == approval
    assert store.get_execution("e") == execution
    assert store.get_execution_for_analysis("a") == execution
    assert store.list_executions() == [execution]
    assert store.list_articles() == [article]
    assert store.list_audit()[0] == event
    assert tuple(store.list_audit()[1:]) == review_events
    assert store.get_analysis("missing") is None
