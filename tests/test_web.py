from decimal import Decimal

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from resolveops.domain.models import PaymentSnapshot
from resolveops.web.app import create_app


def client_with_payment(tmp_path) -> TestClient:
    return TestClient(
        create_app(
            tmp_path / "web.db",
            payments=(
                PaymentSnapshot(
                    id="pay-c",
                    customer_id="c",
                    amount=Decimal("100.00"),
                    amount_refunded=Decimal("0.00"),
                    currency="usd",
                    refundable=True,
                    status="succeeded",
                ),
            ),
        )
    )


def seed_refund_context(client: TestClient) -> None:
    assert client.post("/customers", json={"id": "c"}).status_code == 200
    assert (
        client.post(
            "/knowledge",
            json={
                "id": "k",
                "title": "Refund policy",
                "body": "Refunds require approval.",
                "source_uri": "kb://k",
                "owner": "support",
            },
        ).status_code
        == 200
    )


def test_health(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "web.db"))
    assert client.get("/health").json() == {"status": "ok"}


def test_review_request_is_strict_and_replay_safe(tmp_path) -> None:
    client = client_with_payment(tmp_path)
    seed_refund_context(client)
    response = client.post(
        "/tickets/analyze",
        json={
            "id": "t",
            "customer_id": "c",
            "message": "Refund $10",
            "payment_reference": "pay-c",
        },
    )
    assert response.status_code == 200
    analysis_payload = response.json()
    assert analysis_payload["proposed_action"]["resource_id"] == "pay-c"
    assert analysis_payload["proposed_action"]["resource_kind"] == "payment"
    analysis_id = analysis_payload["id"]

    unknown_field = client.post(
        f"/analyses/{analysis_id}/approve",
        json={"reviewer": "manager@example.com", "unexpected": True},
    )
    assert unknown_field.status_code == 422

    approved = client.post(
        f"/analyses/{analysis_id}/approve",
        json={"reviewer": "manager@example.com", "approve": True},
    )
    assert approved.status_code == 200
    execution = approved.json()["execution"]
    assert execution["state"] == "succeeded"
    assert execution["attempt_count"] == 1
    assert execution["idempotency_key"].startswith("ro_")
    assert execution["action"]["resource_id"] == "pay-c"

    recovered = client.get(f"/analyses/{analysis_id}/execution")
    assert recovered.status_code == 200
    assert recovered.json()["id"] == execution["id"]

    terminal_reconcile = client.post(f"/executions/{execution['id']}/reconcile")
    assert terminal_reconcile.status_code == 409

    replay = client.post(
        f"/analyses/{analysis_id}/approve",
        json={"reviewer": "other@example.com", "approve": True},
    )
    assert replay.status_code == 409


def test_refund_without_payment_reference_cannot_be_approved(tmp_path) -> None:
    client = client_with_payment(tmp_path)
    seed_refund_context(client)
    response = client.post(
        "/tickets/analyze",
        json={"id": "t", "customer_id": "c", "message": "Refund $10"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["disposition"] == "escalate"
    assert payload["proposed_action"] is None
    assert "refund_payment_target_missing" in payload["disposition_reasons"]

    denied = client.post(
        f"/analyses/{payload['id']}/approve",
        json={"reviewer": "manager@example.com", "approve": True},
    )
    assert denied.status_code == 409
    assert "no action" in denied.json()["detail"]


def test_ambiguous_refund_amount_cannot_be_approved(tmp_path) -> None:
    client = client_with_payment(tmp_path)
    seed_refund_context(client)
    response = client.post(
        "/tickets/analyze",
        json={
            "id": "t",
            "customer_id": "c",
            "message": "Refund me",
            "payment_reference": "pay-c",
        },
    )
    analysis_id = response.json()["id"]
    denied = client.post(
        f"/analyses/{analysis_id}/approve",
        json={"reviewer": "manager@example.com", "approve": True},
    )
    assert denied.status_code == 409
    assert "refund_amount_unknown" in denied.json()["detail"]
