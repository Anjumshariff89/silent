"""Step 5: SHA-256 hash chain."""
import hashlib
import json

import pytest

from backend.crypto.hashing import GENESIS_PREV_HASH, canonical_json, compute_log_hash, sha256_hex

# FIPS 180-2 / NIST CAVP SHA-256 test vectors
NIST_VECTORS = [
    (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    (b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
     "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
]


@pytest.mark.parametrize("msg,digest", NIST_VECTORS)
def test_sha256_known_vectors(msg, digest):
    assert sha256_hex(msg) == digest


def test_canonical_json_is_order_independent_and_compact():
    assert canonical_json({"b": 1, "a": "é"}) == canonical_json({"a": "é", "b": 1}) == '{"a":"é","b":1}'


def test_log_hash_matches_independent_computation():
    log = {"agent_id": "a", "event_id": 4624, "event_type": "logon", "severity": "info", "source_host": "h",
           "username": "u", "source_ip": "10.0.0.1", "message": "m", "event_time": "t1", "received_at": "t2",
           "seq_id": 1, "merkle_batch_id": None}  # non-hashed fields are ignored
    content = {k: log[k] for k in ("agent_id", "event_id", "event_type", "severity", "source_host", "username",
                                    "source_ip", "message", "event_time", "received_at")}
    expected = hashlib.sha256((GENESIS_PREV_HASH + json.dumps(content, sort_keys=True, separators=(",", ":"),
                                                              ensure_ascii=False)).encode()).hexdigest()
    assert compute_log_hash(GENESIS_PREV_HASH, log) == expected
    assert compute_log_hash(GENESIS_PREV_HASH, {**log, "message": "m!"}) != expected  # any change -> new hash


def test_bad_prev_hash_rejected():
    with pytest.raises(ValueError):
        compute_log_hash("abc", {})


def test_five_log_chain_links_and_genesis(ingest, client, jwt_headers):
    res = ingest(5)
    assert res[0]["seq_id"] == 1 and res[0]["prev_hash"] == GENESIS_PREV_HASH
    for prev, cur in zip(res, res[1:]):
        assert cur["prev_hash"] == prev["curr_hash"]
    chain = client.get("/api/chain", params={"from_seq": 1}, headers=jwt_headers).json()["links"]
    assert len(chain) == 5 and all(l["hash_valid"] and l["link_valid"] for l in chain)
    # stored hashes recompute from stored content
    logs = client.get("/api/logs", params={"sort": "asc"}, headers=jwt_headers).json()["items"]
    for l in logs:
        assert compute_log_hash(l["prev_hash"], l) == l["curr_hash"]


def test_hashes_are_unique_even_for_identical_events(client, agent_headers):
    from tests.conftest import sample_event
    hashes = {client.post("/api/logs/ingest", json=sample_event(1), headers=agent_headers).json()["curr_hash"]
              for _ in range(3)}
    assert len(hashes) == 3
