"""Narrow Stripe Charge refund integration with explicit recovery semantics."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from urllib.parse import quote

import httpx

from resolveops.domain.audit import object_digest
from resolveops.domain.models import (
    ActionExecution,
    ActionKind,
    ActionProposal,
    ActionResourceKind,
    Approval,
    ExecutionResult,
    ExecutionState,
    PaymentSnapshot,
    ReviewState,
)
from resolveops.domain.outcomes import ActionOutcomeResult, ActionOutcomeState

_ZERO_DECIMAL_CURRENCIES = frozenset(
    {
        "bif",
        "clp",
        "djf",
        "gnf",
        "jpy",
        "kmf",
        "krw",
        "mga",
        "pyg",
        "rwf",
        "vnd",
        "vuv",
        "xaf",
        "xof",
        "xpf",
    }
)
_CONNECT_CHARGE_FIELDS = (
    "application",
    "application_fee",
    "application_fee_amount",
    "on_behalf_of",
    "source_transfer",
    "transfer",
    "transfer_data",
    "transfer_group",
)
_RECOVERABLE_RESPONSE_STATUS_CODES = frozenset({409, 424, 429})


class StripeProviderError(RuntimeError):
    """Sanitized Stripe transport/provider failure whose outcome is not safe to assume."""

    def __init__(self, *, status_code: int, code: str | None, request_id: str | None) -> None:
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        label = code or "provider_error"
        request_suffix = f" request_id={request_id}" if request_id else ""
        super().__init__(
            f"Stripe request failed: status={status_code} code={label}{request_suffix}"
        )


class StripeProtocolError(RuntimeError):
    """Stripe returned data that violates the narrow ResolveOps integration contract."""


class StripeRefundGateway:
    """Exact Charge reader, refund executor/reconciler, and refund outcome verifier."""

    def __init__(
        self,
        *,
        secret_key: str,
        api_version: str,
        base_url: str = "https://api.stripe.com/v1/",
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        idempotency_replay_window: timedelta = timedelta(hours=23),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not secret_key.strip():
            raise ValueError("Stripe secret key must not be empty")
        if not api_version.strip():
            raise ValueError("Stripe API version must be explicit")
        if timeout_seconds <= 0:
            raise ValueError("Stripe timeout must be positive")
        if not timedelta(0) < idempotency_replay_window < timedelta(hours=24):
            raise ValueError("Stripe idempotency replay window must be positive and under 24 hours")
        if not base_url.startswith("https://"):
            raise ValueError("Stripe base URL must use HTTPS")

        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Stripe-Version": api_version,
                "User-Agent": "resolveops-stripe-refund/0.1",
            },
            timeout=timeout_seconds,
            transport=transport,
        )
        self._replay_window = idempotency_replay_window
        self._now = now or (lambda: datetime.now(UTC))

    def close(self) -> None:
        """Close the owned HTTP client."""
        self._client.close()

    @staticmethod
    def _error_code(response: httpx.Response) -> str | None:
        try:
            raw: object = response.json()
        except ValueError:
            return None
        if not isinstance(raw, dict):
            return None
        error = raw.get("error")
        if not isinstance(error, dict):
            return None
        code = error.get("code")
        return code if isinstance(code, str) and code else None

    @classmethod
    def _provider_error(cls, response: httpx.Response) -> StripeProviderError:
        return StripeProviderError(
            status_code=response.status_code,
            code=cls._error_code(response),
            request_id=response.headers.get("Request-Id"),
        )

    @staticmethod
    def _json_object(response: httpx.Response, *, label: str) -> dict[str, object]:
        try:
            raw: object = response.json()
        except ValueError as exc:
            raise StripeProtocolError(f"Stripe {label} response is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise StripeProtocolError(f"Stripe {label} response is not an object")
        return cast(dict[str, object], raw)

    @staticmethod
    def _required_str(payload: dict[str, object], key: str, *, label: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise StripeProtocolError(f"Stripe {label} has invalid {key}")
        return value

    @staticmethod
    def _required_int(payload: dict[str, object], key: str, *, label: str) -> int:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise StripeProtocolError(f"Stripe {label} has invalid {key}")
        return value

    @staticmethod
    def _required_bool(payload: dict[str, object], key: str, *, label: str) -> bool:
        value = payload.get(key)
        if not isinstance(value, bool):
            raise StripeProtocolError(f"Stripe {label} has invalid {key}")
        return value

    @staticmethod
    def _charge_uses_connect(payload: dict[str, object]) -> bool:
        return any(payload.get(key) is not None for key in _CONNECT_CHARGE_FIELDS)

    @staticmethod
    def _currency_exponent(currency: str) -> int:
        return 0 if currency in _ZERO_DECIMAL_CURRENCIES else 2

    @classmethod
    def _from_minor_units(cls, amount: int, currency: str) -> Decimal:
        exponent = cls._currency_exponent(currency)
        scale = Decimal(10) ** exponent
        quantum = Decimal("1") if exponent == 0 else Decimal("0.01")
        return (Decimal(amount) / scale).quantize(quantum)

    @classmethod
    def _to_minor_units(cls, amount: Decimal, currency: str) -> int:
        if amount <= 0:
            raise ValueError("refund amount must be positive")
        exponent = cls._currency_exponent(currency)
        quantum = Decimal("1") if exponent == 0 else Decimal("0.01")
        if amount != amount.quantize(quantum):
            raise ValueError("refund amount has unsupported currency precision")
        scale = Decimal(10) ** exponent
        minor = amount * scale
        if minor != minor.to_integral_value():
            raise ValueError("refund amount cannot be represented in minor units")
        return int(minor)

    def get_payment(self, payment_id: str) -> PaymentSnapshot | None:
        """Read one exact Stripe Charge; customer-level discovery is intentionally absent."""
        if not payment_id.startswith("ch_"):
            return None
        response = self._client.get(f"charges/{quote(payment_id, safe='')}")
        if response.status_code == 404:
            return None
        if not response.is_success:
            raise self._provider_error(response)

        payload = self._json_object(response, label="Charge")
        if payload.get("object") != "charge":
            raise StripeProtocolError("Stripe Charge lookup returned the wrong object type")
        charge_id = self._required_str(payload, "id", label="Charge")
        if charge_id != payment_id:
            raise StripeProtocolError("Stripe Charge lookup returned a mismatched identity")
        currency = self._required_str(payload, "currency", label="Charge")
        if len(currency) != 3 or currency != currency.lower():
            raise StripeProtocolError("Stripe Charge has invalid currency")
        customer_id = self._required_str(payload, "customer", label="Charge")
        amount_captured = self._required_int(payload, "amount_captured", label="Charge")
        amount_refunded = self._required_int(payload, "amount_refunded", label="Charge")
        captured = self._required_bool(payload, "captured", label="Charge")
        paid = self._required_bool(payload, "paid", label="Charge")
        disputed = self._required_bool(payload, "disputed", label="Charge")
        status = self._required_str(payload, "status", label="Charge")
        supported_live_boundary = currency == "usd" and not self._charge_uses_connect(payload)

        refundable = (
            supported_live_boundary
            and captured
            and paid
            and not disputed
            and status == "succeeded"
            and amount_refunded < amount_captured
        )
        return PaymentSnapshot(
            id=charge_id,
            customer_id=customer_id,
            amount=self._from_minor_units(amount_captured, currency),
            amount_refunded=self._from_minor_units(amount_refunded, currency),
            currency=currency,
            refundable=refundable,
            status=status,
        )

    @staticmethod
    def _valid_refund_action(action: ActionProposal) -> bool:
        return (
            action.kind is ActionKind.REFUND
            and action.resource_kind is ActionResourceKind.PAYMENT
            and action.resource_id.startswith("ch_")
            and action.resource_hash is not None
            and action.amount is not None
            and action.currency == "usd"
        )

    @staticmethod
    def _refund_form(
        action: ActionProposal,
        *,
        analysis_id: str,
        approval_id: str,
        idempotency_key: str,
        amount_minor: int,
    ) -> dict[str, str]:
        return {
            "charge": action.resource_id,
            "amount": str(amount_minor),
            "reason": "requested_by_customer",
            "metadata[resolveops_analysis_id]": analysis_id,
            "metadata[resolveops_approval_id]": approval_id,
            "metadata[resolveops_idempotency_hash]": object_digest(idempotency_key),
        }

    @staticmethod
    def _customer_reference(payload: dict[str, object]) -> str | None:
        destination = payload.get("destination_details")
        if not isinstance(destination, dict):
            return None
        card = destination.get("card")
        if not isinstance(card, dict) or card.get("reference_status") != "available":
            return None
        reference = card.get("reference")
        return reference if isinstance(reference, str) and reference else None

    def _validate_refund_object(
        self,
        payload: dict[str, object],
        action: ActionProposal,
        *,
        expected_amount_minor: int,
    ) -> tuple[str, str]:
        if payload.get("object") != "refund":
            raise StripeProtocolError("Stripe refund response returned the wrong object type")
        refund_id = self._required_str(payload, "id", label="Refund")
        charge_id = self._required_str(payload, "charge", label="Refund")
        currency = self._required_str(payload, "currency", label="Refund")
        amount = self._required_int(payload, "amount", label="Refund")
        status = self._required_str(payload, "status", label="Refund")
        if charge_id != action.resource_id:
            raise StripeProtocolError("Stripe refund references a different Charge")
        if currency != action.currency:
            raise StripeProtocolError("Stripe refund currency differs from approved action")
        if amount != expected_amount_minor:
            raise StripeProtocolError("Stripe refund amount differs from approved action")
        return refund_id, status

    def _execution_result_from_refund(
        self,
        payload: dict[str, object],
        action: ActionProposal,
        *,
        expected_amount_minor: int,
    ) -> ExecutionResult:
        refund_id, status = self._validate_refund_object(
            payload,
            action,
            expected_amount_minor=expected_amount_minor,
        )
        if status == "succeeded":
            state = ExecutionState.SUCCEEDED
        elif status in {"pending", "requires_action"}:
            state = ExecutionState.SUBMITTED
        elif status in {"failed", "canceled"}:
            state = ExecutionState.FAILED
        else:
            state = ExecutionState.UNKNOWN
        return ExecutionResult(
            state=state,
            external_reference=refund_id,
            provider_status=status,
            message=f"Stripe refund currently reports status {status}.",
        )

    def execute(
        self,
        action: ActionProposal,
        *,
        approval: Approval,
        idempotency_key: str,
    ) -> ExecutionResult:
        """Submit one exact Charge refund with ResolveOps' stable idempotency identity."""
        if approval.state is not ReviewState.APPROVED:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                message="Stripe refund requires an approved review.",
            )
        if not self._valid_refund_action(action):
            return ExecutionResult(
                state=ExecutionState.FAILED,
                message=(
                    "Stripe refund action is outside the supported verified USD Charge boundary."
                ),
            )
        assert action.amount is not None
        assert action.currency is not None
        try:
            amount_minor = self._to_minor_units(action.amount, action.currency)
        except ValueError:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                message="Stripe refund amount cannot be represented safely in the Charge currency.",
            )

        data = self._refund_form(
            action,
            analysis_id=approval.analysis_id,
            approval_id=approval.id,
            idempotency_key=idempotency_key,
            amount_minor=amount_minor,
        )
        response = self._client.post(
            "refunds",
            data=data,
            headers={"Idempotency-Key": idempotency_key},
        )
        if (
            response.status_code >= 500
            or response.status_code in _RECOVERABLE_RESPONSE_STATUS_CODES
        ):
            raise self._provider_error(response)
        if not response.is_success:
            code = self._error_code(response) or "request_rejected"
            return ExecutionResult(
                state=ExecutionState.FAILED,
                provider_status=code,
                message=f"Stripe rejected the immutable refund request ({code}).",
            )
        return self._execution_result_from_refund(
            self._json_object(response, label="Refund"),
            action,
            expected_amount_minor=amount_minor,
        )

    def reconcile(self, execution: ActionExecution) -> ExecutionResult:
        """Recover by exact refund GET, or conservatively replay the same POST identity."""
        action = execution.action
        if not self._valid_refund_action(action):
            return ExecutionResult(
                state=ExecutionState.FAILED,
                message=(
                    "Stripe refund execution is outside the supported verified USD Charge boundary."
                ),
            )
        assert action.amount is not None
        assert action.currency is not None
        try:
            amount_minor = self._to_minor_units(action.amount, action.currency)
        except ValueError:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                message="Stripe refund amount cannot be represented safely in the Charge currency.",
            )

        if execution.external_reference is not None:
            response = self._client.get(f"refunds/{quote(execution.external_reference, safe='')}")
            if not response.is_success:
                raise self._provider_error(response)
            return self._execution_result_from_refund(
                self._json_object(response, label="Refund"),
                action,
                expected_amount_minor=amount_minor,
            )

        current_time = self._now()
        if current_time.tzinfo is None:
            raise StripeProtocolError("Stripe gateway clock must be timezone-aware")
        age = current_time - execution.created_at
        if age < timedelta(0) or age >= self._replay_window:
            return ExecutionResult(
                state=ExecutionState.UNKNOWN,
                message=(
                    "Stripe refund identity has no external reference and its safe idempotent "
                    "replay window has expired; manual provider investigation is required."
                ),
            )

        data = self._refund_form(
            action,
            analysis_id=execution.analysis_id,
            approval_id=execution.approval_id,
            idempotency_key=execution.idempotency_key,
            amount_minor=amount_minor,
        )
        response = self._client.post(
            "refunds",
            data=data,
            headers={"Idempotency-Key": execution.idempotency_key},
        )
        if (
            response.status_code >= 500
            or response.status_code in _RECOVERABLE_RESPONSE_STATUS_CODES
        ):
            raise self._provider_error(response)
        if not response.is_success:
            code = self._error_code(response) or "request_rejected"
            return ExecutionResult(
                state=ExecutionState.FAILED,
                provider_status=code,
                message=f"Stripe rejected the immutable refund request ({code}).",
            )
        return self._execution_result_from_refund(
            self._json_object(response, label="Refund"),
            action,
            expected_amount_minor=amount_minor,
        )

    def verify(self, execution: ActionExecution) -> ActionOutcomeResult:
        """Read the current refund lifecycle without mutating terminal execution state."""
        if execution.external_reference is None:
            raise StripeProtocolError("Stripe outcome verification requires a refund reference")
        action = execution.action
        if not self._valid_refund_action(action):
            raise StripeProtocolError("Stripe outcome verification requires a valid refund action")
        assert action.amount is not None
        assert action.currency is not None
        amount_minor = self._to_minor_units(action.amount, action.currency)
        response = self._client.get(f"refunds/{quote(execution.external_reference, safe='')}")
        if not response.is_success:
            raise self._provider_error(response)
        payload = self._json_object(response, label="Refund")
        refund_id, status = self._validate_refund_object(
            payload,
            action,
            expected_amount_minor=amount_minor,
        )
        if refund_id != execution.external_reference:
            raise StripeProtocolError("Stripe outcome lookup returned a mismatched refund identity")
        if status == "succeeded":
            state = ActionOutcomeState.VERIFIED
        elif status == "pending":
            state = ActionOutcomeState.PENDING
        elif status == "requires_action":
            state = ActionOutcomeState.REQUIRES_ACTION
        elif status in {"failed", "canceled"}:
            state = ActionOutcomeState.FAILED
        else:
            state = ActionOutcomeState.UNKNOWN
        return ActionOutcomeResult(
            state=state,
            provider_reference=refund_id,
            provider_status=status,
            customer_reference=self._customer_reference(payload),
            message=f"Stripe refund outcome currently reports status {status}.",
        )
