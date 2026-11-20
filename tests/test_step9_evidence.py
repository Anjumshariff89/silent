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
