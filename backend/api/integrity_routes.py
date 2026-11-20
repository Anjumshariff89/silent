"""Hash-chain view (Step 5) and integrity endpoints (Step 6)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request

from backend.api.auth import Jwt, ctx
from backend.crypto.hashing import GENESIS_PREV_HASH, compute_log_hash
from backend.database import repo

router = APIRouter(tags=["integrity"])


@router.get("/api/chain", dependencies=[Jwt])
def get_chain(request: Request, from_seq: Optional[int] = Query(None, ge=1), limit: int = Query(50, ge=1, le=500)) -> dict:
    """Chain links with a per-link recomputation, for the Hash-Chain Visualization page."""
    with ctx(request).engine.connect() as conn:
        if from_seq is None:
            last, _ = repo.chain_head(conn)
            from_seq = max(1, last - limit + 1)
        rows = repo.fetch_chain_rows(conn, from_seq, from_seq + limit - 1)
        prev_row = repo.get_log(conn, from_seq - 1) if from_seq > 1 else None
    links, expected_prev = [], (prev_row["curr_hash"] if prev_row else GENESIS_PREV_HASH)
    for r in rows:
        recomputed = compute_log_hash(r["prev_hash"], r) if r["prev_hash"] else None
        links.append({"seq_id": r["seq_id"], "event_type": r["event_type"], "username": r["username"],
                      "prev_hash": r["prev_hash"], "curr_hash": r["curr_hash"],
                      "hash_valid": recomputed == r["curr_hash"], "link_valid": r["prev_hash"] == expected_prev})
        expected_prev = r["curr_hash"]
    return {"genesis_prev_hash": GENESIS_PREV_HASH, "links": links}
