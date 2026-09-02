from datetime import UTC, datetime
from decimal import Decimal

import pytest

from resolveops.adapters.actions import MockActionExecutor
from resolveops.adapters.billing import MemoryBillingReader
from resolveops.adapters.generator import DeterministicResponseGenerator
from resolveops.adapters.memory import MemoryStore
from resolveops.application.service import ResolveOpsService
from resolveops.domain.models import CustomerProfile, KnowledgeArticle, PaymentSnapshot


@pytest.fixture
def billing_reader() -> MemoryBillingReader:
    return MemoryBillingReader(
        (
            PaymentSnapshot(
                id="pay_cust_1",
                customer_id="cust_1",
                amount=Decimal("2000.00"),
                currency="usd",
            ),
            PaymentSnapshot(
                id="pay_eval",
                customer_id="eval-customer",
                amount=Decimal("2000.00"),
                currency="usd",
            ),
        )
    )


@pytest.fixture
def service(billing_reader: MemoryBillingReader) -> ResolveOpsService:
    service = ResolveOpsService(
        store=MemoryStore(),
        generator=DeterministicResponseGenerator(),
        action_executor=MockActionExecutor(),
        billing_reader=billing_reader,
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
