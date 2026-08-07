from __future__ import annotations

import argparse
import ast
import tomllib
from pathlib import Path

import yaml

parser = argparse.ArgumentParser()
parser.add_argument("--tag", required=True)
args = parser.parse_args()

with Path("pyproject.toml").open("rb") as handle:
    project = tomllib.load(handle)["project"]
version = project["version"]
expected_tag = f"v{version}"
if args.tag != expected_tag:
    raise SystemExit(f"tag mismatch: expected {expected_tag}, got {args.tag}")

required_files = (
    "CHANGELOG.md",
    "CITATION.cff",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "docs/README.md",
    "docs/release-validation.md",
    "docs/releasing.md",
    "docs/security-model.md",
)
for path in required_files:
    if not Path(path).is_file():
        raise SystemExit(f"missing release file: {path}")

version_tree = ast.parse(Path("src/resolveops/_version.py").read_text(encoding="utf-8"))
assignments = {
    target.id: node.value.value
    for node in version_tree.body
    if isinstance(node, ast.Assign)
    and len(node.targets) == 1
    and isinstance((target := node.targets[0]), ast.Name)
    and isinstance(node.value, ast.Constant)
    and isinstance(node.value.value, str)
}
if assignments.get("__version__") != version:
    raise SystemExit("package version does not match pyproject.toml")

citation = yaml.safe_load(Path("CITATION.cff").read_text(encoding="utf-8"))
if str(citation.get("version")) != version:
    raise SystemExit("CITATION.cff version does not match pyproject.toml")
if f"## {version}" not in Path("CHANGELOG.md").read_text(encoding="utf-8"):
    raise SystemExit("CHANGELOG.md has no section for the release version")

for forbidden in (
    "AUDIT_REPORT.md",
    "CODEX_TASK.md",
    "GOVERNANCE.md",
    "INDEPENDENT_VERIFICATION.md",
    "PROJECT_STATUS.md",
    "PUBLISHING.md",
    "ROADMAP.md",
    "START_HERE.md",
    "SUPPORT.md",
    "THREAT_MODEL.md",
):
    if Path(forbidden).exists():
        raise SystemExit(f"obsolete or handoff-only file must not be released: {forbidden}")

print(f"release metadata valid for {args.tag}")
