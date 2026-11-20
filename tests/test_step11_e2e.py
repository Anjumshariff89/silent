"""Step 11: end-to-end integration test of the 6 acceptance scenarios, through the HTTP API.

Each scenario prints a SCENARIO line so the run log doubles as evidence.
Tamper scenarios 2-4 run on SANDBOX COPIES via /api/demo/tamper; the live chain stays intact.
"""
import importlib
import pkgutil
import time
from pathlib import Path

from sqlalchemy import text

import backend
from backend.app.monitor import check_agents_once
from tests.conftest import sample_event

RESULTS: dict[int, str] = {}


def _report(n: int, name: str, ok: bool, evidence: str) -> None:
    RESULTS[n] = "PASS" if ok else "FAIL"
    print(f"\nSCENARIO {n} | {name} | {'PASS' if ok else 'FAIL'} | {evidence}")
    assert ok, f"scenario {n} failed: {evidence}"


def test_six_scenarios_end_to_end(app, client, agent_headers, jwt_headers):
    # 1. Normal ingestion -------------------------------------------------------------------------
    hb = {"agent_id": "agent-e2e", "hostname": "WIN-SYNTH-E2E", "agent_version": "0.1.0", "collector_mode": "simulator"}
    assert client.post("/api/heartbeats", json=hb, headers=agent_headers).status_code == 200
    seqs = [client.post("/api/logs/ingest", json=sample_event(i, agent_id="agent-e2e"), headers=agent_headers).json()["seq_id"]
            for i in range(12)]
    verify = client.post("/api/verify", headers=jwt_headers).json()
    _report(1, "Normal ingestion", seqs == list(range(1, 13)) and verify["result"] == "PASS",
            f"seq_ids {seqs[0]}..{seqs[-1]} sequential, chain verify={verify['result']}")

    # 2. Modified log detected --------------------------------------------------------------------
    r = client.post("/api/demo/tamper", json={"seq_id": 5, "kind": "modify"}, headers=jwt_headers).json()
    issues = [(i["type"], i["seq_id"]) for i in r["verification"]["issues"]]
    _report(2, "Modified log detected", issues == [("modified", 5)] and r["original_unchanged"],
            f"issues={issues}, original_unchanged={r['original_unchanged']}")

    # 3. Deleted log detected ---------------------------------------------------------------------
    r = client.post("/api/demo/tamper", json={"seq_id": 8, "kind": "delete"}, headers=jwt_headers).json()
    issues = [(i["type"], i["seq_id"]) for i in r["verification"]["issues"]]
    _report(3, "Deleted log detected", issues == [("missing", 8)] and r["original_unchanged"],
            f"issues={issues} ({r['verification']['issues'][0]['detail']})")

    # 4. Reordered logs detected ------------------------------------------------------------------
    r = client.post("/api/demo/tamper", json={"seq_id": 3, "kind": "reorder"}, headers=jwt_headers).json()
    types = {i["type"] for i in r["verification"]["issues"]}
    seqs_hit = sorted(i["seq_id"] for i in r["verification"]["issues"])
    _report(4, "Reordered logs detected", types == {"reordered"} and {3, 4} <= set(seqs_hit) and r["original_unchanged"],
            f"types={types}, seq_ids={seqs_hit}")
    inc = client.get("/api/incidents", params={"target": "sandbox"}, headers=jwt_headers).json()
    assert inc["total"] >= 3
    assert client.post("/api/verify", headers=jwt_headers).json()["result"] == "PASS"  # live chain untouched

    # 5. Anchored Merkle root verified ------------------------------------------------------------
    b = client.post("/api/merkle/build", headers=jwt_headers).json()
    a = client.post("/api/blockchain/anchor", json={"batch_id": b["batch_id"]}, headers=jwt_headers).json()
    ok = client.post("/api/proof/verify", json={"batch_id": b["batch_id"], "seq_id": 6}, headers=jwt_headers).json()
    with app.state.ctx.engine.begin() as c:  # temp test DB, synthetic data
        c.execute(text("UPDATE security_logs SET message='edited' WHERE seq_id=6"))
    bad = client.post("/api/proof/verify", json={"batch_id": b["batch_id"]}, headers=jwt_headers).json()
    evidence = client.get(f"/api/evidence/{b['batch_id']}/json", headers=jwt_headers)
    _report(5, "Anchored Merkle root verified",
            ok["result"] == "MATCH" and ok["inclusion_proof_valid"] and bad["result"] == "MISMATCH"
            and a["tx_hash"].startswith("0x") and evidence.status_code == 200,
            f"tx={a['tx_hash'][:14]}… block={a['block_number']} MATCH, then MISMATCH after edit")

    # 6. Agent stopped -> heartbeat timeout -------------------------------------------------------
    s = app.state.ctx.settings
    s.heartbeat_online_s, s.heartbeat_offline_s = 0.3, 0.6
    assert client.post("/api/heartbeats", json=hb, headers=agent_headers).status_code == 200
    status_before = {x["agent_id"]: x["status"] for x in client.get("/api/agents", headers=jwt_headers).json()["items"]}
    time.sleep(0.9)  # agent "stopped": no more heartbeats
    status_after = {x["agent_id"]: x["status"] for x in client.get("/api/agents", headers=jwt_headers).json()["items"]}
    events = check_agents_once(app.state.ctx)
    timeouts = client.get("/api/incidents", params={"type": "heartbeat_timeout"}, headers=jwt_headers).json()["items"]
    _report(6, "Agent stopped, heartbeat timeout detected",
            status_before["agent-e2e"] == "online" and status_after["agent-e2e"] == "offline"
            and len(events) == 1 and timeouts and timeouts[0]["agent_id"] == "agent-e2e",
            f"status {status_before['agent-e2e']} -> {status_after['agent-e2e']}, incident #{timeouts[0]['id'] if timeouts else None}")

    print("\n| Scenario | Result |\n|---|---|")
    names = ["Normal ingestion", "Modified log detected", "Deleted log detected", "Reordered logs detected",
             "Anchored Merkle root verified", "Agent stopped, heartbeat timeout detected"]
    for n, name in enumerate(names, 1):
        print(f"| {n} {name} | {RESULTS[n]} |")


def test_every_backend_module_imports():
    for m in pkgutil.walk_packages(backend.__path__, "backend."):
        if not m.ispkg and m.name != "backend.main":
            importlib.import_module(m.name)


def test_every_api_route_is_exercised_by_a_test(app):
    """Each HTTP/WebSocket route path must be called by at least one test (path prefix match)."""
    tests_text = "\n".join(p.read_text() for p in Path(__file__).parent.glob("test_*.py"))
    missing = []
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith(("/api", "/ws")):
            continue
        prefix = path.split("{", 1)[0]
        if prefix not in tests_text:
            missing.append(path)
    assert not missing, f"routes never called in tests: {missing}"
