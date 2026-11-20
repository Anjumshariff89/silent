"""Step 9: evidence bundle + PDF certificate."""
import copy
import io
import json

import pytest
from pypdf import PdfReader

from backend.app.evidence import DISCLAIMER, REQUIRED_FIELDS
from backend.crypto.offline_verify import verify_bundle


@pytest.fixture
def anchored(client, jwt_headers, ingest):
    ingest(7)
    b = client.post("/api/merkle/build", headers=jwt_headers).json()
    client.post("/api/blockchain/anchor", json={"batch_id": b["batch_id"]}, headers=jwt_headers)
    return b["batch_id"]


def test_json_bundle_fields_and_download_headers(client, jwt_headers, anchored):
    r = client.get(f"/api/evidence/{anchored}/json", headers=jwt_headers)
    assert r.status_code == 200 and "attachment; filename=evidence_batch_1.json" in r.headers["content-disposition"]
    b = r.json()
    for f in REQUIRED_FIELDS:
        assert f in b, f
    assert len(b["logs"]) == 7 and set(b["proofs"]) == {str(i) for i in range(1, 8)}
    assert b["anchor"]["tx_hash"].startswith("0x") and b["anchor"]["onchain_batch_id"]
    assert "explorer_url" in b["anchor"] and b["verification"]["result"] == "MATCH"
    assert b["disclaimer"] == DISCLAIMER


def test_bundle_reverifies_offline_from_json_alone(client, jwt_headers, anchored):
    b = json.loads(client.get(f"/api/evidence/{anchored}/json", headers=jwt_headers).text)
    res = verify_bundle(b)
    assert res["valid"], res["errors"]
    assert all(res["checks"].values())


@pytest.mark.parametrize("mutate,expect", [
    (lambda b: b["logs"][2].__setitem__("username", "attacker"), "log content does not match"),
    (lambda b: b["logs"].pop(3), "expected seq"),
    (lambda b: b["logs"].insert(1, b["logs"].pop(2)), "prev_hash linkage broken"),
    (lambda b: b["batch"].__setitem__("merkle_root", "00" * 32), "recomputed root"),
    (lambda b: b["proofs"]["5"][0].__setitem__("hash", "11" * 32), "inclusion proof fails for seq [5]"),
    (lambda b: b.pop("disclaimer"), "missing fields"),
])
def test_offline_verifier_rejects_tampered_bundle(client, jwt_headers, anchored, mutate, expect):
    b = json.loads(client.get(f"/api/evidence/{anchored}/json", headers=jwt_headers).text)
    bad = copy.deepcopy(b)
    mutate(bad)
    res = verify_bundle(bad)
    assert not res["valid"] and any(expect in e for e in res["errors"]), res["errors"]


def test_pdf_opens_and_contains_disclaimer(client, jwt_headers, anchored):
    r = client.get(f"/api/evidence/{anchored}/pdf", headers=jwt_headers)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    reader = PdfReader(io.BytesIO(r.content))
    txt = " ".join((p.extract_text() or "") for p in reader.pages)
    flat = " ".join(txt.split())
    assert "Tamper-Evidence Certificate" in flat and "MATCH" in flat
    assert "does not prove that the logged events occurred" in flat


def test_evidence_404_for_unknown_batch(client, jwt_headers):
    assert client.get("/api/evidence/42/json", headers=jwt_headers).status_code == 404
    assert client.get("/api/evidence/42/pdf", headers=jwt_headers).status_code == 404


def test_real_mode_bundle_has_quai_network_and_orchard_explorer(tmp_path):
    """Bundle built from a REAL (quai-service) anchor: Quai network name, Orchard QuaiScan link, offline-verifiable."""
    from fastapi.testclient import TestClient
    from backend.app.factory import create_app
    from backend.blockchain.anchor import QuaiServiceAnchorer
    from tests.conftest import TEST_API_KEY, make_settings, sample_event
    from tests.test_step8_blockchain import _emulated_service
    s = make_settings(tmp_path, rpc_url="https://orchard.rpc.quai.network/cyprus1", cyprus1_pk="0x" + "1" * 64,
                      contract_address="0x00aa" + "0" * 36)
    app = create_app(s, run_monitor=False)
    app.state.ctx.anchorer = QuaiServiceAnchorer(s.contract_address, transport=_emulated_service({"anchored": {}}))
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": "admin", "password": TEST_API_KEY}).json()["access_token"]}
        for i in range(4):
            c.post("/api/logs/ingest", json=sample_event(i), headers={"X-API-Key": TEST_API_KEY})
        b = c.post("/api/merkle/build", headers=h).json()
        assert c.post("/api/blockchain/anchor", json={"batch_id": b["batch_id"]}, headers=h).status_code == 200
        bundle = json.loads(c.get(f"/api/evidence/{b['batch_id']}/json", headers=h).text)
        pdf = c.get(f"/api/evidence/{b['batch_id']}/pdf", headers=h).content
    a = bundle["anchor"]
    assert a["mode"] == "REAL" and a["chain_id"] == 15000 and a["network"] == "Quai Orchard Cyprus-1 (testnet)"
    assert a["explorer_url"].startswith("https://orchard.quaiscan.io/tx/0x")
    assert a["contract_explorer_url"] == "https://orchard.quaiscan.io/address/0x00aa" + "0" * 36
    assert "PolygonScan" not in json.dumps(bundle) and "source not verified" in a["explorer_status"]
    assert bundle["verification"]["result"] == "MATCH" and verify_bundle(bundle)["valid"]
    text = " ".join(" ".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(pdf)).pages)
    assert "Quai Orchard Cyprus-1" in text and "orchard.quaiscan.io" in text
