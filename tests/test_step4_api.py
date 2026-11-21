"""Step 4: FastAPI core behaviour."""
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from backend.app.monitor import check_agents_once
from tests.conftest import sample_event


def test_ingest_returns_sequential_seq_ids(client, agent_headers):
    r1 = client.post("/api/logs/ingest", json=sample_event(1), headers=agent_headers)
    r2 = client.post("/api/logs/ingest", json=sample_event(2), headers=agent_headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["seq_id"] == r1.json()["seq_id"] + 1


def test_ingest_without_or_with_wrong_api_key_is_401(client):
    assert client.post("/api/logs/ingest", json=sample_event()).status_code == 401
    assert client.post("/api/logs/ingest", json=sample_event(), headers={"X-API-Key": "nope"}).status_code == 401


@pytest.mark.parametrize("bad", [
    {"event_id": 9999},                       # not a monitored event
    {"event_type": "logoff"},                 # mismatched with 4624
    {"source_ip": "999.1.1.1"},               # invalid IP
    {"event_time": "yesterday"},              # invalid timestamp
    {"agent_id": "bad id with spaces"},       # agent_id pattern
    {"extra_field": "x"},                     # unknown field rejected
])
def test_malformed_body_is_422(client, agent_headers, bad):
    assert client.post("/api/logs/ingest", json=sample_event(**bad), headers=agent_headers).status_code == 422


def test_missing_required_field_is_422(client, agent_headers):
    ev = sample_event()
    del ev["message"]
    assert client.post("/api/logs/ingest", json=ev, headers=agent_headers).status_code == 422


def test_get_logs_requires_jwt_and_supports_filters_and_pagination(client, ingest, jwt_headers, agent_headers):
    ingest(12)
    client.post("/api/logs/ingest", json=sample_event(99, event_id=4672, event_type="special_privileges",
                                                    severity="warning", username="synthetic.admin"),
                headers=agent_headers)
    assert client.get("/api/logs").status_code == 401
    r = client.get("/api/logs", params={"page": 1, "page_size": 5}, headers=jwt_headers).json()
    assert r["total"] == 13 and len(r["items"]) == 5 and r["items"][0]["seq_id"] == 13
    r2 = client.get("/api/logs", params={"page": 3, "page_size": 5}, headers=jwt_headers).json()
    assert [i["seq_id"] for i in r2["items"]] == [3, 2, 1]
    f = client.get("/api/logs", params={"event_id": 4672}, headers=jwt_headers).json()
    assert f["total"] == 1 and f["items"][0]["severity"] == "warning"
    s = client.get("/api/logs", params={"q": "ADMIN"}, headers=jwt_headers).json()
    assert s["total"] == 1
    assert "curr_hash" in r["items"][0] and len(r["items"][0]["curr_hash"]) == 64


def test_login_rejects_bad_password(client):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401


def test_no_update_or_delete_routes_exist(app):
    for route in app.routes:
        methods = getattr(route, "methods", set()) or set()
        assert not ({"PUT", "PATCH", "DELETE"} & methods), route.path


def test_websocket_receives_new_log_live(client, agent_headers, jwt_headers):
    token = jwt_headers["Authorization"].split()[1]
    with client.websocket_connect(f"/ws/live?token={token}") as ws:
        assert ws.receive_json()["type"] == "hello"
        r = client.post("/api/logs/ingest", json=sample_event(5), headers=agent_headers)
        msg = ws.receive_json()
        assert msg["type"] == "log" and msg["data"]["seq_id"] == r.json()["seq_id"]


def test_websocket_rejects_bad_token(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/ws/live?token=bad") as ws:
            ws.receive_json()
    assert e.value.code == 1008


def test_heartbeat_then_stop_flips_agent_offline_and_creates_incident(app, client, agent_headers, jwt_headers):
    s = app.state.ctx.settings
    s.heartbeat_online_s, s.heartbeat_offline_s = 0.5, 1.0
    hb = {"agent_id": "agent-hb", "hostname": "WIN-SYNTH-02", "agent_version": "0.1.0", "collector_mode": "windows"}
    assert client.post("/api/heartbeats", json=hb, headers=agent_headers).status_code == 200
    agents = {a["agent_id"]: a for a in client.get("/api/agents", headers=jwt_headers).json()["items"]}
    assert agents["agent-hb"]["status"] == "online"
    time.sleep(0.7)
    agents = {a["agent_id"]: a for a in client.get("/api/agents", headers=jwt_headers).json()["items"]}
    assert agents["agent-hb"]["status"] == "delayed"
    time.sleep(0.5)
    agents = {a["agent_id"]: a for a in client.get("/api/agents", headers=jwt_headers).json()["items"]}
    assert agents["agent-hb"]["status"] == "offline"
    events = check_agents_once(app.state.ctx)
    assert [e["incident"]["type"] for e in events] == ["heartbeat_timeout"]
    assert check_agents_once(app.state.ctx) == []  # alerted only once
    assert client.get("/api/heartbeats", headers=jwt_headers).json()["items"][0]["agent_id"] == "agent-hb"


def test_health_reports_truthful_status_and_no_secrets(real_app, settings):
    from fastapi.testclient import TestClient
    with TestClient(real_app) as c:
        for path in ("/health", "/api/health"):
            body = c.get(path).json()
            assert body["status"] == "ok"
            assert body["integrations"] == {"blockchain": "NOT CONFIGURED", "database": "SQLITE",
                                            "telegram": "CONSOLE", "windows_event_log": "UNAVAILABLE", "auth": "LOCAL"}
            assert settings.api_key not in str(body) and settings.jwt_secret not in str(body)


def test_concurrent_first_contact_does_not_500(client, agent_headers):
    """Regression: first heartbeat + first events for a new agent arriving at once (seen in live run)."""
    from concurrent.futures import ThreadPoolExecutor
    hb = {"agent_id": "agent-race", "hostname": "h", "agent_version": "0.1.0", "collector_mode": "windows"}
    calls = [("/api/heartbeats", hb)] * 5 + [("/api/logs/ingest", sample_event(i, agent_id="agent-race"))
                                             for i in range(5)]
    with ThreadPoolExecutor(10) as pool:
        codes = list(pool.map(lambda c: client.post(c[0], json=c[1], headers=agent_headers).status_code, calls))
    assert codes == [200] * 10


def test_agent_known_only_from_ingest_is_reported_as_api_not_simulator(client, agent_headers, jwt_headers):
    ev = sample_event(1, agent_id="seed-script")
    assert client.post("/api/logs/ingest", json=ev, headers=agent_headers).status_code == 200
    agents = {a["agent_id"]: a for a in client.get("/api/agents", headers=jwt_headers).json()["items"]}
    assert agents["seed-script"]["collector_mode"] == "api"
