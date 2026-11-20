"""Step 7: Merkle tree, root, proofs, endpoints."""
import hashlib

import pytest

from backend.merkle.tree import build_levels, inclusion_proof, merkle_root, verify_proof

H = [hashlib.sha256(f"log{i}".encode()).hexdigest() for i in range(8)]


def sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def L(h):  # hand-computed leaf
    return sha(b"\x00" + bytes.fromhex(h))


def N(a, b):  # hand-computed node
    return sha(b"\x01" + a + b)


def test_known_4_leaf_tree_matches_hand_computed_root():
    expected = N(N(L(H[0]), L(H[1])), N(L(H[2]), L(H[3]))).hex()
    assert merkle_root(H[:4]) == expected


@pytest.mark.parametrize("n,expected_fn", [
    (1, lambda: L(H[0]).hex()),
    (3, lambda: N(N(L(H[0]), L(H[1])), N(L(H[2]), L(H[2]))).hex()),
    (5, lambda: N(N(N(L(H[0]), L(H[1])), N(L(H[2]), L(H[3]))),
                  N(N(L(H[4]), L(H[4])), N(L(H[4]), L(H[4])))).hex()),
])
def test_odd_leaf_counts(n, expected_fn):
    assert merkle_root(H[:n]) == expected_fn()
    levels = build_levels(H[:n])
    for i in range(n):  # every leaf proves
        assert verify_proof(H[i], inclusion_proof(levels, i), levels[-1][0])


@pytest.mark.parametrize("n", range(1, 9))
def test_all_proofs_verify_for_sizes_1_to_8(n):
    levels = build_levels(H[:n])
    assert all(verify_proof(H[i], inclusion_proof(levels, i), levels[-1][0]) for i in range(n))


def _flip_one_byte(hex_str: str) -> str:
    b = bytearray(bytes.fromhex(hex_str))
    b[0] ^= 0x01
    return b.hex()


def test_proof_with_one_changed_byte_fails():
    levels = build_levels(H[:5])
    root, proof = levels[-1][0], inclusion_proof(levels, 2)
    assert verify_proof(H[2], proof, root)
    assert not verify_proof(_flip_one_byte(H[2]), proof, root)                      # leaf
    bad = [dict(p) for p in proof]
    bad[0]["hash"] = _flip_one_byte(bad[0]["hash"])
    assert not verify_proof(H[2], bad, root)                                        # sibling
    assert not verify_proof(H[2], proof, _flip_one_byte(root))                      # root
    swapped = [dict(p, position="left" if p["position"] == "right" else "right") for p in proof]
    assert not verify_proof(H[2], swapped, root)                                    # position


def test_domain_separation_internal_node_is_not_a_leaf():
    levels = build_levels(H[:4])
    internal = levels[1][0]
    assert not verify_proof(internal, [{"position": "right", "hash": levels[1][1]}], levels[-1][0])


def test_empty_tree_rejected():
    with pytest.raises(ValueError):
        build_levels([])


def test_merkle_endpoints(ingest, client, jwt_headers):
    logs = ingest(5)
    b = client.post("/api/merkle/build", headers=jwt_headers).json()
    assert b["leaf_count"] == 5 and b["from_seq"] == 1 and b["to_seq"] == 5
    assert b["root"] == merkle_root([l["curr_hash"] for l in logs])
    got = client.get(f"/api/merkle/{b['batch_id']}", headers=jwt_headers).json()
    assert got["root"] == b["root"] and got["levels"][-1] == [b["root"]] and got["anchored"] is False
    p = client.get(f"/api/merkle/{b['batch_id']}/proof/3", headers=jwt_headers).json()
    assert p["leaf"] == logs[2]["curr_hash"] and verify_proof(p["leaf"], p["proof"], p["root"])
    assert client.get(f"/api/merkle/{b['batch_id']}/proof/99", headers=jwt_headers).status_code == 404
    assert client.get("/api/merkle/999", headers=jwt_headers).status_code == 404
    assert client.post("/api/merkle/build", headers=jwt_headers).status_code == 400  # nothing left to batch
    ingest(3, start=5)
    b2 = client.post("/api/merkle/build", headers=jwt_headers).json()
    assert (b2["from_seq"], b2["to_seq"], b2["leaf_count"]) == (6, 8, 3)
    logs_page = client.get("/api/logs", params={"sort": "asc"}, headers=jwt_headers).json()["items"]
    assert [l["merkle_batch_id"] for l in logs_page] == [1] * 5 + [2] * 3
    assert client.post("/api/merkle/build", json={"from_seq": 4, "to_seq": 7}, headers=jwt_headers).status_code == 409
