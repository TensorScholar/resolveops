from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from resolveops.adapters.sqlite import SQLiteStore
from resolveops.domain.errors import IntegrityError
from resolveops.domain.models import (
    ActionExecution,
    ActionKind,
    ActionProposal,
    Approval,
    ReviewState,
)


def _create_pre_lifecycle_schema(path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE objects (
                kind TEXT NOT NULL,
                id TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (kind, id)
            );
            CREATE TABLE approval_claims (
                analysis_id TEXT PRIMARY KEY,
                approval_id TEXT UNIQUE NOT NULL
            );
            """
        )


def _approved_review() -> tuple[Approval, ActionProposal]:
    approval = Approval(
        id="apr_upgrade",
        analysis_id="ana_upgrade",
        reviewer="reviewer@example.com",
        state=ReviewState.APPROVED,
    )
    action = ActionProposal(
        kind=ActionKind.REFUND,
        resource_id="charge_upgrade",
        amount=Decimal("10.00"),
        reason="Upgrade fixture refund.",
    )
    return approval, action


def _persist_approval(path, approval: Approval) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO approval_claims(analysis_id,approval_id) VALUES(?,?)",
            (approval.analysis_id, approval.id),
        )
        connection.execute(
            "INSERT INTO objects(kind,id,payload) VALUES('approval',?,?)",
            (approval.id, approval.model_dump_json()),
        )


def test_upgrade_rejects_pre_lifecycle_execution_records(tmp_path) -> None:
    path = tmp_path / "legacy-execution.db"
    _create_pre_lifecycle_schema(path)
    approval, action = _approved_review()
    _persist_approval(path, approval)
    legacy_execution = {
        "id": "exe_upgrade",
        "analysis_id": approval.analysis_id,
        "approval_id": approval.id,
        "action": action.model_dump(mode="json"),
        "success": False,
        "external_reference": None,
        "message": "Legacy executor returned an ambiguous false result.",
        "executed_at": datetime.now(UTC).isoformat(),
    }
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO objects(kind,id,payload) VALUES('execution',?,?)",
            (legacy_execution["id"], json.dumps(legacy_execution)),
        )

    with pytest.raises(IntegrityError, match="legacy execution records"):
        SQLiteStore(path)


def test_upgrade_backfills_verified_current_execution_claim(tmp_path) -> None:
    path = tmp_path / "current-execution.db"
    _create_pre_lifecycle_schema(path)
    approval, action = _approved_review()
    _persist_approval(path, approval)
    execution = ActionExecution(
        id="exe_upgrade",
        analysis_id=approval.analysis_id,
        approval_id=approval.id,
        action=action,
        idempotency_key="ro_upgrade_fixture",
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO objects(kind,id,payload) VALUES('execution',?,?)",
            (execution.id, execution.model_dump_json()),
        )

    store = SQLiteStore(path)

    assert store.get_execution_for_analysis(approval.analysis_id) == execution
    with sqlite3.connect(path) as connection:
        claim = connection.execute(
            """
            SELECT analysis_id,approval_id,execution_id
            FROM execution_claims
            WHERE analysis_id=?
            """,
            (approval.analysis_id,),
        ).fetchone()
    assert claim == (approval.analysis_id, approval.id, execution.id)


def test_upgrade_rejects_approved_review_without_execution(tmp_path) -> None:
    path = tmp_path / "orphaned-approval.db"
    _create_pre_lifecycle_schema(path)
    approval, _ = _approved_review()
    _persist_approval(path, approval)

    with pytest.raises(IntegrityError, match="approved legacy review"):
        SQLiteStore(path)
