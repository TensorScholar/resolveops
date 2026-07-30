from datetime import UTC, datetime
from decimal import Decimal

import pytest

from resolveops.adapters.actions import MockActionExecutor
from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.memory import MemoryStore
from resolveops.application.service import ResolveOpsService
from resolveops.domain.models import CustomerProfile, KnowledgeArticle


@pytest.fixture
def service() -> ResolveOpsService:
    service = ResolveOpsService(
        store=MemoryStore(),
        generator=DeterministicResponseGenerator(),
        action_executor=MockActionExecutor(),
    )
    service.seed_customer(
        CustomerProfile(
            id="cust_1",
            plan="pro",
            lifetime_value=Decimal("1200"),
            account_age_days=300,
        )
    )
    service.seed_article(
        KnowledgeArticle(
            id="kb_refund",
            title="Refund policy",
            body="Refunds up to $250 require human approval.",
            source_uri="kb://refund",
            owner="support",
            updated_at=datetime.now(UTC),
        )
    )
    return service
