"""Direct unit tests for config, schemas and service modules (previously covered only indirectly)."""
import pytest
from pydantic import ValidationError

from backend.api.schemas import HeartbeatIn, IngestIn, RangeIn
from backend.app import config as cfg
from backend.app.anchor_service import onchain_batch_id
from backend.app.integrity_service import integrity_status, run_chain_verification


def _clear(monkeypatch):
    for k in ("MODE", "API_KEY", "JWT_SECRET", "DATABASE_URL", "RPC_URL", "CYPRUS1_PK",
              "CONTRACT_ADDRESS", "CHAIN_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)


def test_config_simulator_defaults(monkeypatch, tmp_path):
    _clear(monkeypatch)
    s = cfg.load_settings(tmp_path / "missing.env")
    assert s.mode == "simulator" and s.api_key == cfg.DEV_API_KEY and s.using_dev_api_key
    assert len(s.jwt_secret) >= 32 and s.chain_id == 15000
    assert s.integration_modes() == {"blockchain": "SIMULATED", "database": "SIMULATED", "telegram": "SIMULATED",
                                     "windows_event_log": "SIMULATED"}
    assert s.database_url.startswith("sqlite:///") and s.database_url.endswith("/local.db")


def test_config_real_mode_requires_keys(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("MODE", "real")
    with pytest.raises(RuntimeError, match="API_KEY and JWT_SECRET"):
        cfg.load_settings(tmp_path / "missing.env")


def test_config_badges_turn_real_only_when_all_keys_set(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("RPC_URL", "https://rpc.example")
    monkeypatch.setenv("CYPRUS1_PK", "0x" + "1" * 64)
    s = cfg.load_settings(tmp_path / "x.env")
    assert s.integration_modes()["blockchain"] == "SIMULATED"  # contract address still missing
    monkeypatch.setenv("CONTRACT_ADDRESS", "0x" + "2" * 40)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u@h/db")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    m = cfg.load_settings(tmp_path / "x.env").integration_modes()
    assert m["blockchain"] == m["database"] == m["telegram"] == "REAL"


def test_settings_repr_hides_secrets(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv("API_KEY", "super-secret-api-key")
    monkeypatch.setenv("CYPRUS1_PK", "0x" + "ab" * 32)
    r = repr(cfg.load_settings(tmp_path / "x.env"))
    assert "super-secret-api-key" not in r and "ab" * 32 not in r


def test_schemas_validation():
    ok = IngestIn(agent_id="a", event_id=4624, event_type="logon", source_host="h", message="m",
                  event_time="2026-01-01T00:00:00", source_ip="-").to_record()
    assert ok["event_time"] == "2026-01-01T00:00:00Z" and ok["source_ip"] is None
    with pytest.raises(ValidationError):
        HeartbeatIn(agent_id="a", hostname="h", collector_mode="linux")
    with pytest.raises(ValidationError):
        RangeIn(from_seq=0)


def test_onchain_batch_id_namespacing():
    a = onchain_batch_id("ab" * 32, 1)
    b = onchain_batch_id("cd" * 32, 1)
    assert a != b and a & ((1 << 64) - 1) == 1 and a < 2 ** 256


def test_integrity_service_status_transitions(app, ingest):
    c = app.state.ctx
    assert integrity_status(c)["status"] == "yellow"  # never verified
    ingest(3)
    assert run_chain_verification(c)["result"] == "PASS"
    assert integrity_status(c)["status"] == "green"
    assert run_chain_verification(c, from_seq=2, to_seq=3)["result"] == "PASS"  # range verify uses predecessor


def test_incidents_resolve_route(client, jwt_headers, ingest):
    ingest(4)
    client.post("/api/demo/tamper", json={"seq_id": 2}, headers=jwt_headers)
    client.post("/api/demo/tamper", json={"seq_id": 3}, headers=jwt_headers)
    assert client.get("/api/incidents", params={"status": "open"}, headers=jwt_headers).json()["total"] == 2
    r = client.post("/api/incidents/resolve", params={"target": "sandbox"}, headers=jwt_headers).json()
    assert r == {"resolved": 2}
    assert client.get("/api/incidents", params={"status": "open"}, headers=jwt_headers).json()["total"] == 0
    assert client.get("/api/incidents", params={"status": "resolved"}, headers=jwt_headers).json()["total"] == 2
    assert client.post("/api/incidents/resolve").status_code == 401


def test_merkle_batches_list_route(client, jwt_headers, ingest):
    ingest(3)
    assert client.get("/api/merkle/batches", headers=jwt_headers).json()["items"] == []
    b = client.post("/api/merkle/build", headers=jwt_headers).json()
    client.post("/api/blockchain/anchor", json={"batch_id": b["batch_id"]}, headers=jwt_headers)
    items = client.get("/api/merkle/batches", headers=jwt_headers).json()["items"]
    assert len(items) == 1 and items[0]["root"] == b["root"] and items[0]["tx_hash"].startswith("0x")
    assert items[0]["mode"] == "SIMULATED"


def test_quai_keys_never_reach_web3_and_badge_stays_truthful(tmp_path):
    """Until the quai-service exists, full Quai keys still give a simulated anchorer and a SIMULATED badge."""
    from fastapi.testclient import TestClient
    from backend.app.factory import create_app
    from tests.conftest import make_settings
    s = make_settings(tmp_path, rpc_url="https://rpc.example", cyprus1_pk="0x" + "1" * 64,
                      contract_address="0x" + "2" * 40)
    app = create_app(s, run_monitor=False)
    assert app.state.ctx.anchorer.mode == "SIMULATED"
    with TestClient(app) as c:
        assert c.get("/api/health").json()["integrations"]["blockchain"] == "SIMULATED"
