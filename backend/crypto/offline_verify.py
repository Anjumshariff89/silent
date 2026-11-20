"""Offline verifier for an evidence bundle. Needs ONLY the JSON file (no server, no database).

Checks: required fields; each log's hash recomputes; chain linkage; contiguous seq ids;
leaf count; Merkle root recomputes; every inclusion proof; anchored root equals root.

    python -m backend.crypto.offline_verify evidence_batch_1.json
Exit code 0 = VALID, 1 = INVALID.

It deliberately uses only the standard library (hashlib/json) so an auditor can read and trust it.
"""
from __future__ import annotations

import hashlib
import json
import sys

REQUIRED = ("schema_version", "generated_at", "batch", "logs", "hash_algorithm", "canonicalization",
            "merkle", "proofs", "anchor", "verification", "disclaimer")


def _sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def _log_hash(prev: str, log: dict, fields: list[str]) -> str:
    content = json.dumps({k: log.get(k) for k in fields}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev + content).encode("utf-8")).hexdigest()


def _leaf(h: str) -> bytes:
    return _sha(b"\x00" + bytes.fromhex(h))


def _root(leaves: list[str]) -> str:
    level = [_leaf(h) for h in leaves]
    while len(level) > 1:
        level = [_sha(b"\x01" + level[i] + (level[i + 1] if i + 1 < len(level) else level[i]))
                 for i in range(0, len(level), 2)]
    return level[0].hex()


def _proof_ok(leaf_hex: str, proof: list[dict], root: str) -> bool:
    acc = _leaf(leaf_hex)
    for p in proof:
        s = bytes.fromhex(p["hash"])
        acc = _sha(b"\x01" + (acc + s if p["position"] == "right" else s + acc))
    return acc.hex() == root


def verify_bundle(bundle: dict) -> dict:
    errors: list[str] = []
    missing = [f for f in REQUIRED if f not in bundle]
    if missing:
        return {"valid": False, "errors": [f"missing fields: {missing}"], "checks": {}}
    b, logs, fields = bundle["batch"], bundle["logs"], bundle.get("hashed_fields")
    if not fields:
        errors.append("hashed_fields missing")
        fields = []
    checks = {}
    # 1. each log hash + linkage
    prev = b["prev_batch_tail_hash"]
    bad_hash, bad_link = [], []
    for log in logs:
        if log["prev_hash"] != prev:
            bad_link.append(log["seq_id"])
        if _log_hash(log["prev_hash"], log, fields) != log["curr_hash"]:
            bad_hash.append(log["seq_id"])
        prev = log["curr_hash"]
    checks["log_hashes"] = not bad_hash
    checks["chain_links"] = not bad_link
    if bad_hash:
        errors.append(f"log content does not match curr_hash at seq {bad_hash}")
    if bad_link:
        errors.append(f"prev_hash linkage broken at seq {bad_link}")
    # 2. sequence + count
    seqs = [l["seq_id"] for l in logs]
    checks["sequence"] = seqs == list(range(b["from_seq"], b["to_seq"] + 1)) and len(logs) == b["leaf_count"]
    if not checks["sequence"]:
        errors.append(f"expected seq {b['from_seq']}-{b['to_seq']} ({b['leaf_count']} logs), got {len(logs)}")
    # 3. merkle root from recomputed hashes
    recomputed = [_log_hash(l["prev_hash"], l, fields) for l in logs]
    root = _root(recomputed) if recomputed else None
    checks["merkle_root"] = root == b["merkle_root"]
    if not checks["merkle_root"]:
        errors.append(f"recomputed root {str(root)[:16]}... != bundle root {b['merkle_root'][:16]}...")
    # 4. proofs
    bad_proofs = [l["seq_id"] for l in logs
                  if not _proof_ok(l["curr_hash"], bundle["proofs"].get(str(l["seq_id"]), []), b["merkle_root"])]
    checks["inclusion_proofs"] = not bad_proofs
    if bad_proofs:
        errors.append(f"inclusion proof fails for seq {bad_proofs}")
    # 5. anchor
    a = bundle["anchor"]
    checks["anchored_root_matches"] = bool(a) and a.get("anchored_root") == b["merkle_root"]
    if not a:
        errors.append("batch is not anchored")
    elif not checks["anchored_root_matches"]:
        errors.append("anchored_root in bundle differs from merkle_root")
    return {"valid": not errors, "errors": errors, "checks": checks, "recomputed_root": root,
            "anchor_mode": a.get("mode") if a else None,
            "note": "Offline check proves internal consistency and that the logs hash to the anchored root. "
                    "For REAL anchors, also confirm on-chain via getAnchor(onchain_batch_id)."}


def main() -> None:  # pragma: no cover - CLI
    if len(sys.argv) != 2:
        print("usage: python -m backend.crypto.offline_verify <bundle.json>")
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        res = verify_bundle(json.load(f))
    print(json.dumps(res, indent=2))
    print("RESULT:", "VALID" if res["valid"] else "INVALID")
    sys.exit(0 if res["valid"] else 1)


if __name__ == "__main__":
    main()
