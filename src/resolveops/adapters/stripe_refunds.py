"""Narrow Stripe Charge refund integration for ResolveOps."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol, cast

from resolveops.domain.errors import ExternalDependencyError, IntegrationContractError
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


class _ChargeService(Protocol):
    def retrieve(
        self,
        charge: str,
        params: dict[str, object] | None = None,
        options: dict[str, object] | None = None,
    ) -> object: ...


class _RefundService(Protocol):
    def create(
        self,
        params: dict[str, object] | None = None,
        options: dict[str, object] | None = None,
    ) -> object: ...

    def retrieve(
        self,
        refund: str,
        params: dict[str, object] | None = None,
        options: dict[str, object] | None = None,
    ) -> object: ...

    def list(
        self,
        params: dict[str, object] | None = None,
        options: dict[str, object] | None = None,
    ) -> object: ...


class _StripeV1(Protocol):
    charges: _ChargeService
    refunds: _RefundService


class StripeClientProtocol(Protocol):
    v1: _StripeV1


_IDEMPOTENCY_METADATA_KEY = "resolveops_idempotency_key"
_ANALYSIS_METADATA_KEY = "resolveops_analysis_id"
_APPROVAL_METADATA_KEY = "resolveops_approval_id"
_SUPPORTED_CURRENCY = "usd"
_SUPPORTED_PAYMENT_METHOD = "card"
_DEFAULT_RETRY_WINDOW = timedelta(hours=23)


def _get(obj: object, key: str, default: object = None) -> object:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _string_id(value: object) -> str | None:
    if isinstance(value, str):
        return value
    nested = _get(value, "id") if value is not None else None
    return nested if isinstance(nested, str) else None


def _metadata(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _minor_to_decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IntegrationContractError(f"Stripe {field} must be a non-negative integer.")
    return (Decimal(value) / Decimal(100)).quantize(Decimal("0.01"))


def _decimal_to_minor(amount: Decimal) -> int:
    if amount <= Decimal("0"):
        raise IntegrationContractError("Stripe refund amount must be positive.")
    scaled = amount * Decimal(100)
    if scaled != scaled.to_integral_value():
        raise IntegrationContractError("Stripe USD refund amount must resolve to whole cents.")
    return int(scaled)


def _http_status(exc: Exception) -> int | None:
    status = getattr(exc, "http_status", None)
    return status if isinstance(status, int) else None


def _error_code(exc: Exception) -> str | None:
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) else None


class StripeRefundAdapter:
    """Read Stripe Charges and submit/reconcile one narrow USD card-refund path."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: StripeClientProtocol | None = None,
        idempotency_retry_window: timedelta = _DEFAULT_RETRY_WINDOW,
    ) -> None:
        if idempotency_retry_window <= timedelta(0) or idempotency_retry_window >= timedelta(
            hours=24
        ):
            raise ValueError("Stripe idempotency retry window must be greater than 0 and under 24h.")
        if client is None:
            if not api_key:
                raise ValueError("Stripe API key is required when no client is supplied.")
            try:
                import stripe
            except ImportError as exc:  # pragma: no cover - exercised by packaging smoke
                raise RuntimeError("Install ResolveOps with the 'stripe' extra.") from exc
            client = cast(
                StripeClientProtocol,
                stripe.StripeClient(api_key, max_network_retries=0),
            )
        self._client = client
        self._idempotency_retry_window = idempotency_retry_window

    def get_payment(self, payment_id: str) -> PaymentSnapshot | None:
        """Retrieve exactly one Stripe Charge and normalize only the supported refund surface."""
        if not payment_id.startswith("ch_"):
            return None
        try:
            charge = self._client.v1.charges.retrieve(payment_id)
        except Exception as exc:
            if _error_code(exc) == "resource_missing" or _http_status(exc) == 404:
                return None
            raise ExternalDependencyError("Stripe charge lookup failed.") from exc

        charge_id = _string_id(_get(charge, "id"))
        if charge_id != payment_id:
            raise IntegrationContractError("Stripe returned a mismatched charge identity.")
        customer_id = _string_id(_get(charge, "customer"))
        if customer_id is None:
            raise IntegrationContractError("Stripe charge has no verifiable customer owner.")
        currency = _get(charge, "currency")
        status = _get(charge, "status")
        if not isinstance(currency, str) or not isinstance(status, str):
            raise IntegrationContractError("Stripe charge is missing currency or status.")

        amount = _minor_to_decimal(_get(charge, "amount"), field="charge amount")
        amount_refunded = _minor_to_decimal(
            _get(charge, "amount_refunded"), field="charge amount_refunded"
        )
        details = _get(charge, "payment_method_details")
        payment_method = _get(details, "type") if details is not None else None
        paid = _get(charge, "paid") is True
        captured = _get(charge, "captured") is True
        disputed = _get(charge, "disputed") is True
        refundable = (
            paid
            and captured
            and not disputed
            and status == "succeeded"
            and currency == _SUPPORTED_CURRENCY
            and payment_method == _SUPPORTED_PAYMENT_METHOD
            and amount_refunded < amount
        )
        return PaymentSnapshot(
            id=charge_id,
            customer_id=customer_id,
            amount=amount,
            amount_refunded=amount_refunded,
            currency=currency,
            refundable=refundable,
            status=status,
        )

    @staticmethod
    def _validate_refund_action(action: ActionProposal) -> None:
        if (
            action.kind is not ActionKind.REFUND
            or action.resource_kind is not ActionResourceKind.PAYMENT
            or not action.resource_id.startswith("ch_")
            or action.resource_hash is None
            or action.amount is None
            or action.currency != _SUPPORTED_CURRENCY
        ):
            raise IntegrationContractError(
                "Stripe refund requires a verified USD Charge target and explicit amount."
            )

    @staticmethod
    def _refund_params(
        action: ActionProposal,
        *,
        analysis_id: str,
        approval_id: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        StripeRefundAdapter._validate_refund_action(action)
        assert action.amount is not None
        return {
            "charge": action.resource_id,
            "amount": _decimal_to_minor(action.amount),
            "reason": "requested_by_customer",
            "metadata": {
                _IDEMPOTENCY_METADATA_KEY: idempotency_key,
                _ANALYSIS_METADATA_KEY: analysis_id,
                _APPROVAL_METADATA_KEY: approval_id,
            },
        }

    @staticmethod
    def _map_refund(refund: object) -> ExecutionResult:
        refund_id = _string_id(_get(refund, "id"))
        status = _get(refund, "status")
        if refund_id is None or not refund_id.startswith("re_") or not isinstance(status, str):
            raise IntegrationContractError("Stripe returned an invalid Refund object.")
        if status in {"failed", "canceled"}:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                external_reference=refund_id,
                provider_status=status,
                message="Stripe refund reached a failed or canceled provider state.",
            )
        if status in {"pending", "requires_action", "succeeded"}:
            return ExecutionResult(
                state=ExecutionState.SUBMITTED,
                external_reference=refund_id,
                provider_status=status,
                message=(
                    "Stripe accepted the refund; customer outcome remains subject to "
                    "post-action verification."
                ),
            )
        return ExecutionResult(
            state=ExecutionState.UNKNOWN,
            external_reference=refund_id,
            provider_status=status,
            message="Stripe returned an unrecognized refund lifecycle state.",
        )

    @staticmethod
    def _known_rejection(exc: Exception) -> ExecutionResult | None:
        status = _http_status(exc)
        if status is not None and 400 <= status < 500 and status not in {409, 424, 429}:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                provider_status=f"stripe_http_{status}",
                message="Stripe rejected the refund without an accepted provider operation.",
            )
        return None

    def execute(
        self,
        action: ActionProposal,
        *,
        approval: Approval,
        idempotency_key: str,
    ) -> ExecutionResult:
        """Submit a refund once using the ResolveOps action identity as Stripe idempotency."""
        if approval.state is not ReviewState.APPROVED:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                message="Stripe refund requires an approved ResolveOps review.",
            )
        params = self._refund_params(
            action,
            analysis_id=approval.analysis_id,
            approval_id=approval.id,
            idempotency_key=idempotency_key,
        )
        try:
            refund = self._client.v1.refunds.create(
                params,
                {"idempotency_key": idempotency_key},
            )
        except Exception as exc:
            rejected = self._known_rejection(exc)
            if rejected is not None:
                return rejected
            raise ExternalDependencyError("Stripe refund outcome is not definitive.") from exc
        return self._map_refund(refund)

    @staticmethod
    def _refund_items(list_result: object) -> Iterable[object]:
        auto_paging_iter = getattr(list_result, "auto_paging_iter", None)
        if callable(auto_paging_iter):
            return cast(Iterable[object], auto_paging_iter())
        data = _get(list_result, "data", ())
        if not isinstance(data, Iterable) or isinstance(data, (str, bytes, Mapping)):
            raise IntegrationContractError("Stripe refund list returned invalid data.")
        if _get(list_result, "has_more", False) is True:
            raise IntegrationContractError(
                "Stripe refund reconciliation requires complete pagination support."
            )
        return cast(Iterable[object], data)

    def _find_refund_by_metadata(self, execution: ActionExecution) -> object | None:
        try:
            result = self._client.v1.refunds.list(
                {"charge": execution.action.resource_id, "limit": 100}
            )
        except Exception as exc:
            raise ExternalDependencyError("Stripe refund reconciliation lookup failed.") from exc
        matches: list[object] = []
        for refund in self._refund_items(result):
            metadata = _metadata(_get(refund, "metadata", {}))
            if metadata.get(_IDEMPOTENCY_METADATA_KEY) == execution.idempotency_key:
                matches.append(refund)
        if len(matches) > 1:
            raise IntegrationContractError(
                "Stripe contains multiple refunds for one ResolveOps idempotency identity."
            )
        return matches[0] if matches else None

    def reconcile(self, execution: ActionExecution) -> ExecutionResult:
        """Resolve a lost/uncertain Stripe response without issuing a fresh action identity."""
        self._validate_refund_action(execution.action)
        if execution.external_reference is not None:
            if not execution.external_reference.startswith("re_"):
                raise IntegrationContractError("Stripe execution has an invalid refund reference.")
            try:
                refund = self._client.v1.refunds.retrieve(execution.external_reference)
            except Exception as exc:
                raise ExternalDependencyError("Stripe refund retrieval failed.") from exc
            return self._map_refund(refund)

        existing = self._find_refund_by_metadata(execution)
        if existing is not None:
            return self._map_refund(existing)

        age = datetime.now(UTC) - execution.created_at
        if age >= self._idempotency_retry_window:
            return ExecutionResult(
                state=ExecutionState.UNKNOWN,
                provider_status="manual_reconciliation_required",
                message=(
                    "No matching Stripe refund was found and the safe idempotent replay "
                    "window has expired."
                ),
            )

        params = self._refund_params(
            execution.action,
            analysis_id=execution.analysis_id,
            approval_id=execution.approval_id,
            idempotency_key=execution.idempotency_key,
        )
        try:
            refund = self._client.v1.refunds.create(
                params,
                {"idempotency_key": execution.idempotency_key},
            )
        except Exception as exc:
            rejected = self._known_rejection(exc)
            if rejected is not None:
                return rejected
            raise ExternalDependencyError("Stripe reconciliation outcome is not definitive.") from exc
        return self._map_refund(refund)
