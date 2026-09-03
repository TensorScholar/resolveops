"""Post-action outcome observations distinct from command execution state."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field

from resolveops.domain.models import StrictModel, utc_now


class ActionOutcomeState(StrEnum):
    """Latest provider-observed customer outcome; observations are never terminal history."""

    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    REQUIRES_ACTION = "requires_action"
    UNKNOWN = "unknown"


class ActionOutcomeResult(StrictModel):
    """Provider result returned by an outcome verifier before audit persistence."""

    state: ActionOutcomeState
    provider_reference: str = Field(min_length=1, max_length=512)
    provider_status: str | None = Field(default=None, max_length=120)
    customer_reference: str | None = Field(default=None, max_length=512)
    message: str = Field(min_length=1, max_length=2_000)


class ActionOutcomeObservation(StrictModel):
    """Append-only observation of an external action's customer-visible lifecycle."""

    execution_id: str = Field(min_length=1, max_length=320)
    state: ActionOutcomeState
    provider_reference: str = Field(min_length=1, max_length=512)
    provider_status: str | None = Field(default=None, max_length=120)
    customer_reference: str | None = Field(default=None, max_length=512)
    message: str = Field(min_length=1, max_length=2_000)
    observed_at: AwareDatetime = Field(default_factory=utc_now)
