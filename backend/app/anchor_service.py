"""Anchoring + proof verification services (used by the API and the standalone verifier process)."""
from __future__ import annotations

from sqlalchemy import text

from backend.app.context import AppContext
from backend.blockchain.anchor import AlreadyAnchored, AnchorError, explorer_tx_url
from backend.crypto.hashing import compute_log_hash
from backend.database import repo
from backend.merkle.tree import build_levels, inclusion_proof, verify_proof

NOTE = ("MATCH means the logs in this batch, re-hashed now, produce the root that was anchored at block {block}. "
        "It proves the commitment is unchanged since anchoring. It does NOT prove the events themselves occurred.")


class ServiceError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _batch(conn, batch_id: int) -> dict:
    r = conn.execute(text("SELECT * FROM merkle_batches WHERE batch_id=:b"), {"b": batch_id}).first()
    if not r:
        raise ServiceError(404, f"Merkle batch {batch_id} not found")
    return dict(r._mapping)


def get_anchor_row(conn, batch_id: int) -> dict | None:
    r = conn.execute(text("SELECT * FROM blockchain_anchors WHERE batch_id=:b"), {"b": batch_id}).first()
    return dict(r._mapping) if r else None


def onchain_batch_id(genesis_curr_hash: str, batch_id: int) -> int:
    """uint256 contract key = (first 64 bits of the genesis log hash << 64) | batch_id.

    Namespacing by the genesis hash keeps keys unique per log database, so a reset/new database
    never collides with batches another database already anchored on the same contract.
    """
    return (int(genesis_curr_hash[:16], 16) << 64) | batch_id


def anchor_batch(c: AppContext, batch_id: int) -> dict:
    with c.engine.connect() as conn:
        b = _batch(conn, batch_id)
        if get_anchor_row(conn, batch_id):
            raise ServiceError(409, f"Batch {batch_id} is already anchored")
        genesis = repo.get_log(conn, 1)
    if not genesis or not genesis["curr_hash"]:
        raise ServiceError(409, "Genesis log (seq 1) missing: cannot derive on-chain batch key")
    key = onchain_batch_id(genesis["curr_hash"], batch_id)
    try:
        res = c.anchorer.anchor(b["root"], key)
    except AlreadyAnchored as exc:
        raise ServiceError(409, str(exc))
    except AnchorError as exc:
        raise ServiceError(503, str(exc))
    row = {"batch_id": batch_id, "onchain_batch_id": str(key), "root": b["root"], "mode": c.anchorer.mode, "chain_id": c.anchorer.chain_id,
           "tx_hash": res["tx_hash"], "block_number": res["block_number"], "block_timestamp": res["block_timestamp"],
           "contract_address": c.anchorer.contract_address,
           "explorer_url": explorer_tx_url(c.anchorer.chain_id, res["tx_hash"]) if c.anchorer.mode == "REAL" else None,
           "created_at": repo.now_iso()}
    with c.engine.begin() as conn:
        conn.execute(text("INSERT INTO blockchain_anchors(batch_id, onchain_batch_id, root, mode, chain_id, tx_hash, block_number,"
                          " block_timestamp, contract_address, explorer_url, created_at) VALUES (:batch_id,:onchain_batch_id,:root,"
                          ":mode,:chain_id,:tx_hash,:block_number,:block_timestamp,:contract_address,:explorer_url,"
                          ":created_at)"), row)
    c.hub.broadcast_from_thread("anchor", {"batch_id": batch_id, "tx_hash": row["tx_hash"], "mode": row["mode"]})
    return {k: v for k, v in row.items() if k != "created_at"}


def recompute_batch(conn, b: dict) -> tuple[list[dict], list[str], list[str]]:
    """Return (rows, recomputed_leaves, problems) from CURRENT database content.

    Leaves are recomputed from log content (not copied from stored curr_hash), so editing a log's
    content changes its leaf even if the attacker leaves the stored hash untouched.
    """
    rows = repo.fetch_chain_rows(conn, b["from_seq"], b["to_seq"])
    problems = []
    if len(rows) != b["leaf_count"]:
        problems.append(f"batch expects {b['leaf_count']} logs, found {len(rows)} (deleted or inserted logs)")
    seqs = [r["seq_id"] for r in rows]
    if seqs != list(range(b["from_seq"], b["from_seq"] + len(rows))):
        problems.append("sequence numbers in batch are not contiguous")
    leaves = [compute_log_hash(r["prev_hash"], r) if r["prev_hash"] else "0" * 64 for r in rows]
    return rows, leaves, problems


def verify_batch(c: AppContext, batch_id: int, seq_id: int | None = None, record: bool = True) -> dict:
    with c.engine.connect() as conn:
        b = _batch(conn, batch_id)
        anchor_row = get_anchor_row(conn, batch_id)
        rows, leaves, problems = recompute_batch(conn, b)
    local_root = build_levels(leaves)[-1][0] if leaves else None
    onchain = None
    if anchor_row:
        try:
            onchain = c.anchorer.get_anchor(int(anchor_row["onchain_batch_id"]))
        except AnchorError as exc:
            raise ServiceError(503, str(exc))
        if onchain is None:
            problems.append("database records an anchor for this batch, but none exists on-chain under its key")
    anchored_root = onchain["root"] if onchain else None
    if anchor_row is None:
        result = "NOT_ANCHORED"
    elif anchored_root and local_root == anchored_root and not problems:
        result = "MATCH"
    else:
        result = "MISMATCH"
    proof_valid = None
    if seq_id is not None:
        if not (b["from_seq"] <= seq_id <= b["to_seq"]):
            raise ServiceError(404, f"seq_id {seq_id} not in batch {batch_id}")
        idx = next((i for i, r in enumerate(rows) if r["seq_id"] == seq_id), None)
        if idx is None or not anchored_root:
            proof_valid = False
        else:  # proof from the ORIGINAL stored tree, checked against the anchored root with the CURRENT leaf
            import json as _json
            stored_levels = _json.loads(b["levels_json"])
            proof_valid = verify_proof(leaves[idx], inclusion_proof(stored_levels, seq_id - b["from_seq"]),
                                       anchored_root)
    out = {"batch_id": batch_id, "result": result, "local_root": local_root, "anchored_root": anchored_root,
           "stored_root": b["root"], "leaf_count": b["leaf_count"], "logs_found": len(rows), "problems": problems,
           "inclusion_proof_valid": proof_valid, "mode": c.anchorer.mode,
           "onchain_batch_id": anchor_row["onchain_batch_id"] if anchor_row else None,
           "tx_hash": anchor_row["tx_hash"] if anchor_row else None,
           "block_number": anchor_row["block_number"] if anchor_row else None,
           "explorer_url": anchor_row["explorer_url"] if anchor_row else None,
           "note": NOTE.format(block=anchor_row["block_number"] if anchor_row else "?")}
    if record:
        with c.engine.begin() as conn:
            v = repo.record_verification(conn, kind="proof", result=result, checked_count=len(rows),
                                         batch_id=batch_id, issues=[{"detail": p} for p in problems])
            out["verification_id"], out["verified_at"] = v["id"], v["verified_at"]
            if result == "MISMATCH":
                desc = (f"Merkle root mismatch for batch {batch_id}: local {str(local_root)[:12]}… vs anchored "
                        f"{str(anchored_root)[:12]}…" + (f" ({'; '.join(problems)})" if problems else ""))
                channel, sent = c.alerter.send(desc)
                inc = repo.create_incident(conn, type="merkle_mismatch", batch_id=batch_id, description=desc,
                                           verification_id=v["id"], alert_channel=channel, alert_sent=sent)
                c.hub.broadcast_from_thread("incident", inc)
    return out


def blockchain_status(c: AppContext) -> dict:
    a = c.anchorer
    with c.engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM blockchain_anchors")).scalar()
        last = conn.execute(text("SELECT batch_id, tx_hash, block_number, explorer_url, mode FROM blockchain_anchors"
                                 " ORDER BY batch_id DESC LIMIT 1")).first()
    return {"mode": a.mode, "chain_id": a.chain_id, "connected": a.connected(), "contract_address": a.contract_address,
            "anchor_wallet": getattr(a, "address", None), "latest_block": a.latest_block(),
            "anchored_batches": count, "last_anchor": dict(last._mapping) if last else None}
