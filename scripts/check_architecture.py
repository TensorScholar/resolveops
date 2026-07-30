from pathlib import Path

FORBIDDEN = {
    "src/resolveops/domain": ("fastapi", "sqlite3", "typer", "uvicorn"),
    "src/resolveops/application": ("fastapi", "typer", "uvicorn"),
}

violations: list[str] = []
for directory, tokens in FORBIDDEN.items():
    for path in Path(directory).rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if f"import {token}" in text or f"from {token}" in text:
                violations.append(f"{path}: imports {token}")
if violations:
    raise SystemExit("\n".join(violations))
print("architecture check passed")
