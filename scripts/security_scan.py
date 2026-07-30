import ast
from pathlib import Path

FORBIDDEN_CALLS = {"eval", "exec"}
violations = []
for path in Path("src").rglob("*.py"):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
                violations.append(f"{path}:{node.lineno}: forbidden {node.func.id}")
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"loads", "load"}:
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "pickle":
                    violations.append(f"{path}:{node.lineno}: pickle deserialization")
            for keyword in node.keywords:
                if (
                    keyword.arg == "shell"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    violations.append(f"{path}:{node.lineno}: shell=True")
if violations:
    raise SystemExit("\n".join(violations))
print("static security scan passed")
