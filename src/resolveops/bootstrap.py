"""Composition root."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from resolveops.adapters.actions import MockActionExecutor
from resolveops.adapters.billing import MemoryBillingReader
from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.memory import MemoryStore
from resolveops.adapters.sqlite import SQLiteStore
from resolveops.application.service import ResolveOpsService
from resolveops.domain.models import PaymentSnapshot


def build_service(
    database: str | Path | None = None,
    *,
    payments: Iterable[PaymentSnapshot] = (),
) -> ResolveOpsService:
    store = SQLiteStore(database) if database else MemoryStore()
    return ResolveOpsService(
        store=store,
        generator=DeterministicResponseGenerator(),
        action_executor=MockActionExecutor(),
        billing_reader=MemoryBillingReader(payments),
    )
