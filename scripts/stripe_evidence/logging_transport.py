"""Sanitized HTTP evidence tee and single-fault injector.

Never persists raw secrets. Preserves stable provider identity
(Request-Id, Idempotency-Key, ch_/re_/evt_/cus_ IDs, status codes).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx

REDACTED = "***REDACTED***"

_SECRET_VALUE_RE = re.compile(
    r"(sk_(?:test|live)_[A-Za-z0-9]+|whsec_[A-Za-z0-9]+|Bearer\s+sk_[A-Za-z0-9_]+)"
)
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "secret_key",
        "secret",
        "endpoint_secret",
        "api_key",
        "card_number",
        "cvc",
        "exp_month",
        "exp_year",
        "token",
    }
)


def _redact_string(value: str) -> str:
    if _SECRET_VALUE_RE.search(value):
        return REDACTED
    return value


def sanitize_headers(headers: httpx.Headers) -> dict[str, str]:
    """Copy headers with secrets redacted; stable IDs preserved."""
    cleaned: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered == "authorization" or lowered in _SENSITIVE_KEYS:
            cleaned[key] = REDACTED
        else:
            cleaned[key] = _redact_string(value)
    return cleaned


def sanitize_json(value: Any, *, _in_error: bool = False) -> Any:
    """Recursively sanitize decoded JSON; keep codes/IDs, drop error messages."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            is_secret_key = lowered in _SENSITIVE_KEYS
            is_error_message = _in_error and lowered == "message"
            is_secret_value = isinstance(item, str) and bool(_SECRET_VALUE_RE.search(item))
            if is_secret_key or is_error_message or is_secret_value:
                cleaned[key] = REDACTED
            else:
                cleaned[key] = sanitize_json(
                    item, _in_error=_in_error or str(key).lower() == "error"
                )
        return cleaned
    if isinstance(value, list):
        return [sanitize_json(item, _in_error=_in_error) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def sanitize_body(content: bytes, content_type: str) -> dict[str, Any]:
    """Return a sanitized summary of a request/response body (no raw secrets)."""
    lowered = content_type.lower()
    if "json" in lowered:
        try:
            raw: Any = json.loads(content.decode())
        except (UnicodeDecodeError, ValueError):
            return {
                "encoding": "json",
                "length": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        return {
            "encoding": "json",
            "length": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "body": sanitize_json(raw),
        }
    if "x-www-form-urlencoded" in lowered or b"=" in content:
        try:
            parsed = parse_qs(content.decode(), keep_blank_values=True)
        except (UnicodeDecodeError, ValueError):
            return {
                "encoding": "form",
                "length": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        cleaned: dict[str, Any] = {}
        for key, values in parsed.items():
            if key.lower() in _SENSITIVE_KEYS:
                cleaned[key] = REDACTED
            else:
                cleaned[key] = [_redact_string(v) for v in values]
        return {
            "encoding": "form",
            "length": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "body": cleaned,
        }
    return {
        "encoding": "raw",
        "length": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


class TeeTransport(httpx.BaseTransport):
    """Delegate to another transport while recording sanitized evidence."""

    def __init__(
        self,
        delegate: httpx.BaseTransport,
        *,
        sink: list[dict[str, Any]] | None = None,
        log_path: Path | None = None,
    ) -> None:
        self._delegate = delegate
        self.records: list[dict[str, Any]] = sink if sink is not None else []
        self._log_path = log_path

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        request_headers = sanitize_headers(request.headers)
        request_ct = request.headers.get("content-type", "application/x-www-form-urlencoded")
        request_body = sanitize_body(request.content, request_ct)
        response = self._delegate.handle_request(request)
        response_ct = response.headers.get("content-type", "application/json")
        record: dict[str, Any] = {
            "method": request.method,
            "path": request.url.path,
            "request_headers": request_headers,
            "request_body": request_body,
            "idempotency_key": request.headers.get("Idempotency-Key"),
            "status_code": response.status_code,
            "response_headers": sanitize_headers(response.headers),
            "request_id": response.headers.get("Request-Id"),
            "response_body": sanitize_body(response.content, response_ct),
        }
        self.records.append(record)
        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        return response

    def close(self) -> None:
        close = getattr(self._delegate, "close", None)
        if callable(close):
            close()


class FaultOnceTransport(httpx.BaseTransport):
    """Forward once to the delegate, then raise timeout to simulate ambiguity.

    The provider side effect has happened inside the delegate, but the caller
    observes only a transport failure. Later calls pass through untouched so
    reconciliation with the same body/key can be proved duplicate-free.
    """

    def __init__(self, delegate: httpx.BaseTransport, *, fail_next_posts: int = 1) -> None:
        if fail_next_posts < 1:
            raise ValueError("fail_next_posts must be positive")
        self._delegate = delegate
        self._remaining = fail_next_posts
        self.forwarded_bodies: list[bytes] = []
        self.forwarded_keys: list[str | None] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        is_refund_post = request.method == "POST" and "/v1/refunds" in request.url.path
        if is_refund_post and self._remaining > 0:
            self._remaining -= 1
            self.forwarded_bodies.append(bytes(request.content))
            self.forwarded_keys.append(request.headers.get("Idempotency-Key"))
            response = self._delegate.handle_request(request)
            _ = response.status_code
            raise httpx.ReadTimeout("simulated ambiguous timeout after forward", request=request)
        return self._delegate.handle_request(request)

    def close(self) -> None:
        close = getattr(self._delegate, "close", None)
        if callable(close):
            close()
