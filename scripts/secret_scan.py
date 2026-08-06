from __future__ import annotations

import re
from pathlib import Path

PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{20,}\b"),
}
EXCLUDED_PARTS = {".git", ".venv", "build", "dist", "htmlcov", ".mypy_cache", ".ruff_cache"}
BINARY_SUFFIXES = {
    ".7z",
    ".bin",
    ".db",
    ".docx",
    ".gz",
    ".ico",
    ".jpg",
    ".jpeg",
    ".pdf",
    ".png",
    ".pyc",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".whl",
    ".xlsx",
    ".zip",
}

violations: list[str] = []
for path in Path(".").rglob("*"):
    if not path.is_file() or EXCLUDED_PARTS.intersection(path.parts):
        continue
    if path.suffix.lower() in BINARY_SUFFIXES or path.stat().st_size > 5_000_000:
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    for name, pattern in PATTERNS.items():
        if pattern.search(text):
            violations.append(f"{path}: {name}")

if violations:
    raise SystemExit("\n".join(sorted(violations)))
print("secret scan passed")
