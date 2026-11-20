"""Shared fixtures: an isolated app on a temp SQLite DB with simulator integrations."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import Settings  # noqa: E402
from backend.app.factory import create_app  # noqa: E402

TEST_API_KEY = "test-api-key"


def make_settings(tmp_path: Path, **over) -> Settings:
    base = dict(mode="simulator", api_key=TEST_API_KEY, jwt_secret="test-jwt-secret-" + "x" * 32,
                database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    base.update(over)
    return Settings(**base)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def app(settings):
    return create_app(settings, run_monitor=False)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def agent_headers():
    return {"X-API-Key": TEST_API_KEY}


@pytest.fixture
def jwt_headers(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": TEST_API_KEY})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def sample_event(i: int = 0, **over) -> dict:
    ev = {"agent_id": "agent-test", "event_id": 4624, "event_type": "logon", "severity": "info",
          "source_host": "WIN-SYNTH-01", "username": f"synthetic.user{i % 5}", "source_ip": f"10.0.0.{10 + i % 200}",
          "message": f"An account was successfully logged on (synthetic #{i})",
          "event_time": f"2026-11-20T10:{i // 60 % 60:02d}:{i % 60:02d}Z"}
    ev.update(over)
    return ev


@pytest.fixture
def ingest(client, agent_headers):
    def _ingest(n: int, start: int = 0) -> list[dict]:
        out = []
        for i in range(start, start + n):
            r = client.post("/api/logs/ingest", json=sample_event(i), headers=agent_headers)
            assert r.status_code == 200, r.text
            out.append(r.json())
        return out
    return _ingest
