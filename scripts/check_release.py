import argparse
import tomllib
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--tag", required=True)
args = parser.parse_args()
with Path("pyproject.toml").open("rb") as handle:
    version = tomllib.load(handle)["project"]["version"]
expected = f"v{version}"
if args.tag != expected:
    raise SystemExit(f"tag mismatch: expected {expected}, got {args.tag}")
for path in ("CHANGELOG.md", "CITATION.cff", "README.md", "SECURITY.md"):
    if not Path(path).is_file():
        raise SystemExit(f"missing release file: {path}")
print(f"release metadata valid for {args.tag}")
