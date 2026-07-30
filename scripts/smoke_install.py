from resolveops import __version__
from resolveops.demo import run_demo

assert __version__ == "0.1.0rc1"
result = run_demo()
assert result["metrics"]["resolution_rate"] == 1.0
print("installed-wheel smoke passed")
