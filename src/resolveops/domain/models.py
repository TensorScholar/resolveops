"""Strict domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

StrictMoney = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=12, decimal_places=2)]
StrictCost = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=14, decimal_places=6)]


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class Channel(StrEnum):
    EMAIL = "email"
    CHAT = "chat"
    WEB = "web"


class IntentKind(StrEnum):
    INFORMATION = "information"
    REFUND = "refund"
    PLAN_CHANGE = "plan_change"
    CANCELLATION = "cancellation"
    ACCOUNT_ACCESS = "account_access"
    UNKNOWN = "unknown"


class Disposition(StrEnum):
    RESPOND = "respond"
    REVIEW_REQUIRED = "review_required"
    ESCALATE = "escalate"
    DENY = "deny"


class ActionKind(StrEnum):
    REFUND = "refund"
    PLAN_CHANGE = "plan_change"
    CANCELLATION = "cancellation"


class ReviewState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ExecutionState(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"

    @property
    def terminal(self) -> bool:
        return self in {ExecutionState.SUCCEEDED, ExecutionState.FAILED}


class Ticket(StrictModel):
    id: str = Field(default_factory=lambda: f"tkt_{uuid4().hex}")
    customer_id: str
    message: str = Field(min_length=1, max_length=20_000)
    channel: Channel = Channel.WEB
    received_at: AwareDatetime = Field(default_factory=utc_now)


class CustomerProfile(StrictModel):
    id: str
    plan: str = "free"
    lifetime_value: StrictMoney = Decimal("0")
    account_age_days: int = Field(default=0, ge=0)
    refund_count_90d: int = Field(default=0, ge=0)
    risk_flags: tuple[str, ...] = ()


class KnowledgeArticle(StrictModel):
    id: str
    title: str
    body: str = Field(min_length=1)
    source_uri: str
    owner: str
    approved: bool = True
    updated_at: AwareDatetime = Field(default_factory=utc_now)
    expires_at: AwareDatetime | None = None

    @property
    def is_current(self) -> bool:
        return self.approved and (self.expires_at is None or self.expires_at > utc_now())


class Citation(StrictModel):
    article_id: str
    title: str
    source_uri: str
    excerpt: str
    score: float = Field(ge=0, le=1)
    updated_at: AwareDatetime
    article_hash: str | None = None


class ActionProposal(StrictModel):
    kind: ActionKind
    resource_id: str
    amount: StrictMoney | None = None
    target_plan: str | None = None
    reason: str


class AnalysisResult(StrictModel):
    id: str = Field(default_factory=lambda: f"ana_{uuid4().hex}")
    ticket_id: str
    intent: IntentKind
    summary: str
    draft_reply: str
    citations: tuple[Citation, ...] = ()
    confidence: float = Field(ge=0, le=1)
    disposition: Disposition
    disposition_reasons: tuple[str, ...] = ()
    proposed_action: ActionProposal | None = None
    created_at: AwareDatetime = Field(default_factory=utc_now)


class Approval(StrictModel):
    id: str = Field(default_factory=lambda: f"apr_{uuid4().hex}")
    analysis_id: str
    reviewer: str = Field(min_length=1, max_length=320)
    state: ReviewState
    note: str = Field(default="", max_length=2_000)
    created_at: AwareDatetime = Field(default_factory=utc_now)


class ActionExecution(StrictModel):
    id: str = Field(default_factory=lambda: f"exe_{uuid4().hex}")
    analysis_id: str
    approval_id: str
    action: ActionProposal
    idempotency_key: str = Field(min_length=1, max_length=255)
    state: ExecutionState = ExecutionState.PENDING
    attempt_count: int = Field(default=0, ge=0)
    external_reference: str | None = Field(default=None, max_length=512)
    provider_status: str | None = Field(default=None, max_length=120)
    message: str = Field(
        default="Execution claimed; provider outcome not yet recorded.",
        min_length=1,
        max_length=2_000,
    )
    created_at: AwareDatetime = Field(default_factory=utc_now)
    updated_at: AwareDatetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> ActionExecution:
        if self.updated_at < self.created_at:
            raise ValueError("execution updated_at cannot precede created_at")
        if self.state is ExecutionState.PENDING:
            if self.attempt_count != 0:
                raise ValueError("pending execution cannot have provider attempts")
            if self.external_reference is not None or self.provider_status is not None:
                raise ValueError("pending execution cannot have provider result data")
        elif self.attempt_count == 0:
            raise ValueError("non-pending execution must have at least one provider attempt")
        if self.state in {ExecutionState.SUBMITTED, ExecutionState.SUCCEEDED}:
            if not self.external_reference:
                raise ValueError("submitted or succeeded execution requires external reference")
        return self


class ExecutionResult(StrictModel):
    state: ExecutionState
    message: str = Field(min_length=1, max_length=2_000)
    external_reference: str | None = Field(default=None, max_length=512)
    provider_status: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_provider_result(self) -> ExecutionResult:
        if self.state is ExecutionState.PENDING:
            raise ValueError("pending is reserved for an unattempted local execution claim")
        if self.state in {ExecutionState.SUBMITTED, ExecutionState.SUCCEEDED}:
            if not self.external_reference:
                raise ValueError(
                    "submitted or succeeded provider result requires external reference"
                )
        return self


class Outcome(StrictModel):
    ticket_id: str
    resolved: bool
    escalated: bool
    human_minutes: int = Field(default=0, ge=0)
    csat: int | None = Field(default=None, ge=1, le=5)
    model_cost_usd: StrictCost = Decimal("0")
    recorded_at: AwareDatetime = Field(default_factory=utc_now)


class PolicySettings(StrictModel):
    minimum_confidence: float = Field(default=0.65, ge=0, le=1)
    minimum_citations: int = Field(default=1, ge=0)
    maximum_article_age_days: int = Field(default=180, ge=1)
    maximum_refund: StrictMoney = Decimal("250")
    allowed_actions: frozenset[ActionKind] = frozenset(
        {ActionKind.REFUND, ActionKind.PLAN_CHANGE, ActionKind.CANCELLATION}
    )


class PolicyDecision(StrictModel):
    disposition: Disposition
    reasons: tuple[str, ...]
    action_allowed: bool


class AuditEventDraft(StrictModel):
    event_type: str = Field(min_length=1, max_length=120)
    entity_id: str = Field(min_length=1, max_length=320)
    payload: dict[str, object]


class AuditEvent(StrictModel):
    sequence: int
    event_type: str
    entity_id: str
    payload: dict[str, object]
    occurred_at: AwareDatetime = Field(default_factory=utc_now)
    previous_hash: str
    event_hash: str


class EvaluationCase(StrictModel):
    id: str
    ticket: Ticket
    customer: CustomerProfile
    expected_intent: IntentKind
    expected_disposition: Disposition | None = None
    expected_article_ids: frozenset[str] = frozenset()


class EvaluationSummary(StrictModel):
    cases: int
    intent_accuracy: float
    disposition_accuracy: float | None
    citation_recall: float
    unsafe_action_rate: float
