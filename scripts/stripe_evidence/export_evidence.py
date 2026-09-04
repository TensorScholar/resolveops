"""Offline evidence export: audit artifacts, hashes, manifest, secret scan."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SECRET_PATTERNS = {
    "stripe_test_key": re.compile(r"\bsk_test_[A-Za-z0-9]+\b"),
    "stripe_live_key": re.compile(r"\bsk_live_[A-Za-z0-9]+\b"),
    "webhook_secret": re.compile(r"\bwhsec_[A-Za-z0-9]+\b"),
    "bearer_secret": re.compile(r"Bearer\s+sk_[A-Za-z0-9_]+"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
}


def scan_text_for_secrets(text: str) -> list[str]:
    """Return sorted pattern names found in text (empty means clean)."""
    found: list[str] = []
    for name, pattern in _SECRET_PATTERNS.items():
        if pattern.search(text):
            found.append(name)
    return sorted(found)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str) + "\n")


def _model_rows(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        dump = item.model_dump(mode="json")
        if isinstance(dump, dict):
            rows.append({str(k): v for k, v in dump.items()})
    return rows


def _external_claims(store: Any) -> list[dict[str, Any]]:
    path_value = getattr(store, "path", None)
    if isinstance(path_value, str | Path) and Path(path_value).exists():
        try:
            with closing(sqlite3.connect(str(path_value))) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "external_event_claims" not in tables:
                    return []
                rows = connection.execute(
                    "SELECT unique_key,identity_hash,audit_sequence "
                    "FROM external_event_claims ORDER BY unique_key"
                ).fetchall()
                return [
                    {
                        "unique_key": unique_key,
                        "identity_hash": identity_hash,
                        "audit_sequence": audit_sequence,
                    }
                    for unique_key, identity_hash, audit_sequence in rows
                ]
        except sqlite3.Error:
            return []
    claims = getattr(store, "_audit_event_claims", None)
    if isinstance(claims, dict):
        return [
            {"unique_key": key, "identity": list(value)} for key, value in sorted(claims.items())
        ]
    return []


def assert_no_secrets_in_dir(path: Path) -> None:
    """Fail closed if any exported text file contains secret material."""
    violations: list[str] = []
    for candidate in sorted(path.rglob("*")):
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            continue
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        found = scan_text_for_secrets(text)
        for name in found:
            violations.append(f"{candidate.name}: {name}")
    if violations:
        raise ValueError("secret material in evidence export: " + "; ".join(violations))


def export_evidence(
    *,
    store: Any,
    out_dir: str | Path,
    run_id: str,
    api_version: str,
    repo_rev: str,
    expected_livemode: bool = False,
) -> Path:
    """Export sanitized evidence plus manifest; return manifest path."""
    if not run_id.strip():
        raise ValueError("run_id must not be empty")
    if not api_version.strip():
        raise ValueError("api_version must not be empty")
    if not repo_rev.strip():
        raise ValueError("repo_rev must not be empty")

    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    audit_rows = _model_rows(store.list_audit())
    execution_rows = _model_rows(store.list_executions())
    analysis_rows = _model_rows(store.list_analyses())
    outcomes_rows = _model_rows(store.list_outcomes())
    claim_rows = _external_claims(store)

    _write_jsonl(directory / "audit.jsonl", audit_rows)
    _write_jsonl(directory / "executions.jsonl", execution_rows)
    _write_jsonl(directory / "analyses.jsonl", analysis_rows)
    _write_jsonl(directory / "outcomes.jsonl", outcomes_rows)
    (directory / "external_event_claims.json").write_text(
        json.dumps(claim_rows, sort_keys=True, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    files: dict[str, str] = {}
    for name in (
        "audit.jsonl",
        "executions.jsonl",
        "analyses.jsonl",
        "outcomes.jsonl",
        "external_event_claims.json",
    ):
        files[name] = sha256_file(directory / name)

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "api_version": api_version,
        "repo_rev": repo_rev,
        "expected_livemode": expected_livemode,
        "store_type": type(store).__name__,
        "counts": {
            "audit_events": len(audit_rows),
            "executions": len(execution_rows),
            "analyses": len(analysis_rows),
            "outcomes": len(outcomes_rows),
            "external_event_claims": len(claim_rows),
        },
        "files": files,
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    assert_no_secrets_in_dir(directory)
    return manifest_path
