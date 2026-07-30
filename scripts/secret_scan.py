import re
from pathlib import Path

PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
}
violations = []
for root in ("src", "tests", "examples", "docs"):
    directory = Path(root)
    if not directory.exists():
        continue
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".xlsx", ".docx", ".pdf", ".zip"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                violations.append(f"{path}: {name}")
if violations:
    raise SystemExit("\n".join(violations))
print("secret scan passed")
