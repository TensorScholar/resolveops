import ast
from pathlib import Path

FORBIDDEN = {
    Path("src/resolveops/domain"): {
        "fastapi",
        "sqlite3",
        "typer",
        "uvicorn",
        "resolveops.adapters",
        "resolveops.application",
        "resolveops.web",
    },
    Path("src/resolveops/application"): {
        "fastapi",
        "sqlite3",
        "typer",
        "uvicorn",
        "resolveops.adapters",
        "resolveops.web",
    },
    Path("src/resolveops/ports"): {
        "fastapi",
        "sqlite3",
        "typer",
        "uvicorn",
        "resolveops.adapters",
        "resolveops.application",
        "resolveops.web",
    },
}


def imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


violations: list[str] = []
for directory, forbidden_modules in FORBIDDEN.items():
    for path in directory.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for imported in imported_modules(tree):
            for forbidden in forbidden_modules:
                if imported == forbidden or imported.startswith(f"{forbidden}."):
                    violations.append(f"{path}: imports forbidden module {imported}")

if violations:
    raise SystemExit("\n".join(sorted(violations)))
print("architecture check passed")
