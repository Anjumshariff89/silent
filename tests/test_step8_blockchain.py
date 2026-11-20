"""Step 8: anchoring (simulator; and REAL web3 path against a local Hardhat node when available)."""
import os
import re

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
    assert a["mode"] == "SIMULATED" and a["root"] == b["root"] and a["chain_id"] == 80002
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


def test_web3_anchorer_never_exposes_key():
    from backend.blockchain.anchor import Web3Anchorer
    key = "0x" + "11" * 32
    a = Web3Anchorer("http://127.0.0.1:1", key, "0x" + "22" * 20, chain_id=80002)
    assert key not in repr(a) and key[2:] not in repr(a)
    from backend.blockchain.anchor import AnchorError
    with pytest.raises(AnchorError) as e:
        a.anchor("aa" * 32, 1)
    assert key[2:] not in str(e.value)


HARDHAT_RPC = os.getenv("HARDHAT_RPC_URL")


@pytest.mark.skipif(not HARDHAT_RPC, reason="HARDHAT_RPC_URL not set (local Hardhat node with deployed LogAnchor)")
def test_real_web3_mode_against_local_hardhat(tmp_path):
    """Exercises the REAL web3.py code path end-to-end on a local chain (not Amoy)."""
    from fastapi.testclient import TestClient
    from tests.conftest import TEST_API_KEY, sample_event
    s = make_settings(tmp_path, amoy_rpc_url=HARDHAT_RPC, anchor_private_key=os.environ["HARDHAT_TEST_KEY"],
                      contract_address=os.environ["HARDHAT_CONTRACT"], chain_id=31337)
    with TestClient(create_app(s, run_monitor=False)) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": "admin", "password": TEST_API_KEY}).json()["access_token"]}
        for i in range(4):
            c.post("/api/logs/ingest", json=sample_event(i), headers={"X-API-Key": TEST_API_KEY})
        b = c.post("/api/merkle/build", headers=h).json()
        a = c.post("/api/blockchain/anchor", json={"batch_id": b["batch_id"]}, headers=h).json()
        assert a["mode"] == "REAL" and a["tx_hash"].startswith("0x") and a["block_number"] > 0
        onchain = c.app.state.ctx.anchorer.get_anchor(int(a["onchain_batch_id"]))
        assert onchain["root"] == b["root"]
        assert c.post("/api/proof/verify", json={"batch_id": b["batch_id"]}, headers=h).json()["result"] == "MATCH"


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
