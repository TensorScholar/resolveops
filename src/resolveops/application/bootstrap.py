"""Composition root."""

from __future__ import annotations

from pathlib import Path

from resolveops.adapters.actions import MockActionExecutor
from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.memory import MemoryStore
from resolveops.adapters.sqlite import SQLiteStore
from resolveops.application.service import ResolveOpsService


def build_service(database: str | Path | None = None) -> ResolveOpsService:
    store = SQLiteStore(database) if database else MemoryStore()
    return ResolveOpsService(
        store=store,
        generator=DeterministicResponseGenerator(),
        action_executor=MockActionExecutor(),
    )
