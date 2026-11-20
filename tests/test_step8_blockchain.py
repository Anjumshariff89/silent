"""Step 8: anchoring on Quai Orchard (simulator, and the quai-service client / real Node service)."""
import os
import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app.factory import create_app
from tests.conftest import make_settings


def _anchor_first_batch(client, jwt_headers, ingest, n=6):
    ingest(n)
    b = client.post("/api/merkle/build", headers=jwt_headers).json()
    a = client.post("/api/blockchain/anchor", json={"batch_id": b["batch_id"]}, headers=jwt_headers)
    assert a.status_code == 200, a.text
    return b, a.json()


def test_simulator_anchor_returns_tx_block_timestamp(client, jwt_headers, ingest):
    b, a = _anchor_first_batch(client, jwt_headers, ingest)
    assert a["mode"] == "SIMULATED" and a["root"] == b["root"] and a["chain_id"] == 15000  # simulator reports the configured Quai Cyprus-1 CHAIN_ID
    assert re.fullmatch(r"0x[0-9a-f]{64}", a["tx_hash"])
    assert isinstance(a["block_number"], int) and a["block_number"] > 0
    assert a["block_timestamp"].endswith("Z") and a["explorer_url"] is None
    st = client.get("/api/blockchain/status", headers=jwt_headers).json()
    assert st["mode"] == "SIMULATED" and st["anchored_batches"] == 1 and st["last_anchor"]["tx_hash"] == a["tx_hash"]
    assert client.post("/api/blockchain/anchor", json={"batch_id": b["batch_id"]}, headers=jwt_headers).status_code == 409
    assert client.post("/api/blockchain/anchor", json={"batch_id": 99}, headers=jwt_headers).status_code == 404


def test_proof_verify_match_then_mismatch_after_one_log_altered(app, client, jwt_headers, ingest):
    b, _ = _anchor_first_batch(client, jwt_headers, ingest)
    ok = client.post("/api/proof/verify", json={"batch_id": b["batch_id"], "seq_id": 3}, headers=jwt_headers).json()
    assert ok["result"] == "MATCH" and ok["local_root"] == ok["anchored_root"] and ok["inclusion_proof_valid"] is True
    assert "does NOT prove the events themselves occurred" in ok["note"]
    with app.state.ctx.engine.begin() as c:  # attacker edits content only (temp DB, synthetic data)
        c.execute(text("UPDATE security_logs SET username='attacker' WHERE seq_id=3"))
    bad = client.post("/api/proof/verify", json={"batch_id": b["batch_id"], "seq_id": 3}, headers=jwt_headers).json()
    assert bad["result"] == "MISMATCH" and bad["local_root"] != bad["anchored_root"]
    assert bad["inclusion_proof_valid"] is False
    inc = client.get("/api/incidents", params={"type": "merkle_mismatch"}, headers=jwt_headers).json()["items"]
    assert len(inc) == 1 and inc[0]["batch_id"] == b["batch_id"]
    # unaffected log in the same batch still fails root match (batch-level), but its own leaf proof is valid
    other = client.post("/api/proof/verify", json={"batch_id": b["batch_id"], "seq_id": 1}, headers=jwt_headers).json()
    assert other["result"] == "MISMATCH" and other["inclusion_proof_valid"] is True


def test_full_rewrite_attack_is_caught_by_anchor(app, client, jwt_headers, ingest):
    """Attacker edits a log AND recomputes the entire hash chain so /api/verify passes; anchor still catches it."""
    from backend.crypto.hashing import GENESIS_PREV_HASH, compute_log_hash
    from backend.database import repo
    b, _ = _anchor_first_batch(client, jwt_headers, ingest)
    eng = app.state.ctx.engine
    with eng.begin() as c:
        c.execute(text("UPDATE security_logs SET message='nothing happened' WHERE seq_id=2"))
        prev = GENESIS_PREV_HASH
        for r in repo.fetch_chain_rows(c):
            h = compute_log_hash(prev, r)
            c.execute(text("UPDATE hash_chain SET prev_hash=:p, curr_hash=:h WHERE seq_id=:s"),
                      {"p": prev, "h": h, "s": r["seq_id"]})
            prev = h
    assert client.post("/api/verify", headers=jwt_headers).json()["result"] == "PASS"  # chain alone is fooled
    r = client.post("/api/proof/verify", json={"batch_id": b["batch_id"]}, headers=jwt_headers).json()
    assert r["result"] == "MISMATCH"


def test_tail_truncation_caught_by_anchor(app, client, jwt_headers, ingest):
    b, _ = _anchor_first_batch(client, jwt_headers, ingest)
    with app.state.ctx.engine.begin() as c:
        c.execute(text("DELETE FROM hash_chain WHERE seq_id=6"))
        c.execute(text("DELETE FROM security_logs WHERE seq_id=6"))
    assert client.post("/api/verify", headers=jwt_headers).json()["result"] == "PASS"  # shorter chain still valid
    r = client.post("/api/proof/verify", json={"batch_id": b["batch_id"]}, headers=jwt_headers).json()
    assert r["result"] == "MISMATCH" and "expects 6 logs, found 5" in r["problems"][0]


def test_not_anchored(client, jwt_headers, ingest):
    ingest(3)
    b = client.post("/api/merkle/build", headers=jwt_headers).json()
    r = client.post("/api/proof/verify", json={"batch_id": b["batch_id"]}, headers=jwt_headers).json()
    assert r["result"] == "NOT_ANCHORED"


def test_simulator_ledger_is_write_once(tmp_path):
    from backend.blockchain.anchor import AlreadyAnchored, SimulatedChain
    ch = SimulatedChain(tmp_path / "l.json")
    a1 = ch.anchor("aa" * 32, 1)
    a2 = ch.anchor("bb" * 32, 2)
    assert a2["block_number"] == a1["block_number"] + 1
    with pytest.raises(AlreadyAnchored):
        ch.anchor("cc" * 32, 1)
    assert ch.get_anchor(1)["root"] == "aa" * 32 and ch.get_anchor(3) is None


def test_verifier_service_runs_separately(tmp_path, capsys):
    from fastapi.testclient import TestClient
    from backend.app.factory import build_context
    from backend.verifier_service import run_once
    from tests.conftest import TEST_API_KEY, sample_event
    s = make_settings(tmp_path)
    with TestClient(create_app(s, run_monitor=False)) as api:
        for i in range(12):
            api.post("/api/logs/ingest", json=sample_event(i), headers={"X-API-Key": TEST_API_KEY})
    report = run_once(build_context(s), min_batch=10)  # new context = separate from the API/agent
    assert report["chain"] == "PASS" and report["built"] == 1 and report["anchored"].startswith("0x")
    assert report["batches"] == {1: "MATCH"}


def test_two_databases_can_share_one_contract_without_key_collision(tmp_path):
    """Regression (found live): a fresh DB restarts batch_id at 1; on-chain keys must not collide."""
    from fastapi.testclient import TestClient
    from tests.conftest import TEST_API_KEY, sample_event
    shared = tmp_path / "shared_chain.json"
    results = []
    for name in ("db1", "db2"):
        (tmp_path / name).mkdir()
        app = create_app(make_settings(tmp_path / name), run_monitor=False)
        from backend.blockchain.anchor import SimulatedChain
        app.state.ctx.anchorer = SimulatedChain(shared)  # same "contract" for both databases
        with TestClient(app) as c:
            h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": "admin", "password": TEST_API_KEY}).json()["access_token"]}
            for i in range(3):
                c.post("/api/logs/ingest", json=sample_event(i), headers={"X-API-Key": TEST_API_KEY})
            b = c.post("/api/merkle/build", headers=h).json()
            r = c.post("/api/blockchain/anchor", json={"batch_id": b["batch_id"]}, headers=h)
            assert r.status_code == 200, r.text
            results.append(r.json())
            assert c.post("/api/proof/verify", json={"batch_id": 1}, headers=h).json()["result"] == "MATCH"
    assert results[0]["batch_id"] == results[1]["batch_id"] == 1
    assert results[0]["onchain_batch_id"] != results[1]["onchain_batch_id"]
    assert int(results[0]["onchain_batch_id"]) & ((1 << 64) - 1) == 1


def test_editing_stored_onchain_key_is_mismatch_not_downgrade(app, client, jwt_headers, ingest):
    b, _ = _anchor_first_batch(client, jwt_headers, ingest)
    with app.state.ctx.engine.begin() as c:
        c.execute(text("UPDATE blockchain_anchors SET onchain_batch_id='12345' WHERE batch_id=:b"), {"b": b["batch_id"]})
    r = client.post("/api/proof/verify", json={"batch_id": b["batch_id"]}, headers=jwt_headers).json()
    assert r["result"] == "MISMATCH" and "none exists on-chain" in r["problems"][0]


# ----------------------------------------------------------------------------- quai-service client (REAL path)
import httpx  # noqa: E402

from backend.blockchain.anchor import AlreadyAnchored, AnchorError, QuaiServiceAnchorer  # noqa: E402


def _emulated_service(state):
    """httpx transport that behaves like backend/blockchain/quai-service (contract per PROJECT_STATE.md)."""
    def handler(req: httpx.Request):
        if req.url.path == "/status":
            return httpx.Response(200, json={"mode": "REAL", "chain_id": 15000, "rpc_chain_id": 15000, "connected": True,
                                             "wallet_address": "0x0027" + "a" * 36, "latest_block": 8305618,
                                             "broadcast_allowed": state.get("allow", True)})
        if req.url.path == "/anchor" and req.method == "POST":
            body = __import__("json").loads(req.content)
            if not state.get("allow", True):
                return httpx.Response(403, json={"detail": "broadcasting is disabled"})
            if body["batch_id"] in state["anchored"]:
                return httpx.Response(409, json={"detail": "already anchored"})
            state["anchored"][body["batch_id"]] = body["root"]
            return httpx.Response(200, json={"tx_hash": "0x" + "11" * 32, "block_number": 8305620,
                                             "block_timestamp": "2026-11-20T18:00:00Z",
                                             "explorer_url": "https://orchard.quaiscan.io/tx/0x" + "11" * 32})
        parts = req.url.path.strip("/").split("/")
        if parts[0] == "anchor" and len(parts) >= 2:
            bid = parts[1]
            if bid not in state["anchored"]:
                return httpx.Response(404, json={"detail": "not anchored"})
            if len(parts) == 3:
                return httpx.Response(200, json={"root": state["anchored"][bid], "tx_hash": "0x" + "11" * 32,
                                                 "block_number": 8305620, "block_timestamp": "2026-11-20T18:00:00Z"})
            return httpx.Response(200, json={"root": state["anchored"][bid], "block_timestamp": "2026-11-20T18:00:00Z"})
        return httpx.Response(404, json={"detail": "not found"})
    return httpx.MockTransport(handler)


def test_quai_service_client_paths():
    state = {"anchored": {}}
    a = QuaiServiceAnchorer("0x00aa" + "0" * 36, transport=_emulated_service(state))
    assert a.mode == "REAL" and a.connected() and a.latest_block() == 8305618 and a.address.startswith("0x0027")
    r = a.anchor("ab" * 32, 7)
    assert r["tx_hash"].startswith("0x") and r["explorer_url"].startswith("https://orchard.quaiscan.io/tx/")
    assert a.get_anchor(7)["root"] == "ab" * 32 and a.get_anchor(8) is None
    assert a.find_anchor_tx(7)["tx_hash"] == r["tx_hash"]
    with pytest.raises(AlreadyAnchored):
        a.anchor("ab" * 32, 7)
    state["allow"] = False
    with pytest.raises(AnchorError, match="HTTP 403"):
        a.anchor("cd" * 32, 9)


def test_quai_service_unreachable_is_503_from_api(tmp_path):
    """REAL keys set but quai-service down: anchoring returns 503, nothing is faked."""
    from fastapi.testclient import TestClient
    from tests.conftest import TEST_API_KEY, sample_event
    s = make_settings(tmp_path, rpc_url="https://orchard.rpc.quai.network/cyprus1", cyprus1_pk="0x" + "1" * 64,
                      contract_address="0x00aa" + "0" * 36)
    app = create_app(s, run_monitor=False)
    app.state.ctx.anchorer = QuaiServiceAnchorer(s.contract_address, base_url="http://127.0.0.1:9")  # nothing listens
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": "admin", "password": TEST_API_KEY}).json()["access_token"]}
        assert c.get("/api/health").json()["integrations"]["blockchain"] == "REAL"
        for i in range(3):
            c.post("/api/logs/ingest", json=sample_event(i), headers={"X-API-Key": TEST_API_KEY})
        b = c.post("/api/merkle/build", headers=h).json()
        r = c.post("/api/blockchain/anchor", json={"batch_id": b["batch_id"]}, headers=h)
        assert r.status_code == 503 and "unreachable" in r.json()["detail"]
        assert c.get("/api/blockchain/status", headers=h).json()["connected"] is False


def test_python_never_holds_the_quai_private_key(tmp_path):
    s = make_settings(tmp_path, rpc_url="https://x", cyprus1_pk="0x" + "ab" * 32, contract_address="0x00aa" + "0" * 36)
    a = create_app(s, run_monitor=False).state.ctx.anchorer
    assert isinstance(a, QuaiServiceAnchorer)
    assert "ab" * 32 not in repr(a) and "ab" * 32 not in str(vars(a))


SERVICE_DIR = Path(__file__).resolve().parents[1] / "backend" / "blockchain" / "quai-service"


def _free_port():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


@pytest.mark.skipif(not shutil.which("node") or not (SERVICE_DIR / "node_modules").exists(),
                    reason="node or quai-service node_modules missing")
def test_real_node_quai_service_simulated_mode_end_to_end(tmp_path):
    """Starts the real Node quai-service without keys and drives it from Python."""
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k not in ("RPC_URL", "CYPRUS1_PK", "CONTRACT_ADDRESS")}
    env["QUAI_SERVICE_PORT"] = str(port)
    # run from a temp cwd so the project .env (if any) is not what decides the mode: the service reads ../../../.env,
    # so blank the keys explicitly instead
    env.update({"RPC_URL": "", "CYPRUS1_PK": "", "CONTRACT_ADDRESS": ""})
    proc = subprocess.Popen(["node", "server.js"], cwd=SERVICE_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        a = QuaiServiceAnchorer("0x00aa" + "0" * 36, base_url=f"http://127.0.0.1:{port}")
        for _ in range(50):
            if a.status():
                break
            time.sleep(0.1)
        st = a.status()
        assert st["mode"] == "SIMULATED" and st["chain_id"] == 15000 and st["broadcast_allowed"] is False
        assert a.connected() is False
        with pytest.raises(AnchorError, match="HTTP 403"):  # broadcast gate comes first
            a.anchor("ab" * 32, 1)
    finally:
        proc.terminate()
        out = proc.communicate(timeout=10)[0]
    assert "mode=SIMULATED" in out and "listening on http://127.0.0.1:" in out
