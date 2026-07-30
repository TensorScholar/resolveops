import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from resolveops.web.app import create_app


def test_health(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "web.db"))
    assert client.get("/health").json() == {"status": "ok"}
