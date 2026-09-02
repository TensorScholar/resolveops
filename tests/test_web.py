import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from resolveops.web.app import create_app


def test_health(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "web.db"))
    assert client.get("/health").json() == {"status": "ok"}


def test_review_request_is_strict_and_replay_safe(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "web.db"))
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
    response = client.post(
        "/tickets/analyze",
        json={"id": "t", "customer_id": "c", "message": "Refund $10"},
    )
    assert response.status_code == 200
    analysis_id = response.json()["id"]

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


def test_ambiguous_refund_cannot_be_approved(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "web.db"))
    client.post("/customers", json={"id": "c"})
    client.post(
        "/knowledge",
        json={
            "id": "k",
            "title": "Refund policy",
            "body": "Refunds require approval.",
            "source_uri": "kb://k",
            "owner": "support",
        },
    )
    response = client.post(
        "/tickets/analyze",
        json={"id": "t", "customer_id": "c", "message": "Refund me"},
    )
    analysis_id = response.json()["id"]
    denied = client.post(
        f"/analyses/{analysis_id}/approve",
        json={"reviewer": "manager@example.com", "approve": True},
    )
    assert denied.status_code == 409
    assert "refund_amount_unknown" in denied.json()["detail"]
