"""Merkle endpoints: build a batch, read it, get an inclusion proof."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from backend.api.auth import Jwt, ctx
from backend.api.schemas import RangeIn
from backend.database import repo
from backend.merkle.tree import build_levels, inclusion_proof

router = APIRouter(prefix="/api/merkle", tags=["merkle"])


def build_batch(engine, from_seq: int | None = None, to_seq: int | None = None) -> dict:
    with engine.begin() as conn:
        if from_seq is None:  # default: everything not yet batched
            from_seq = conn.execute(text("SELECT min(seq_id) FROM security_logs WHERE merkle_batch_id IS NULL")).scalar()
            if from_seq is None:
                raise HTTPException(status_code=400, detail="No unbatched logs to build a Merkle batch from")
        rows = repo.fetch_chain_rows(conn, from_seq, to_seq)
        if not rows:
            raise HTTPException(status_code=400, detail="No logs in requested range")
        if any(r["merkle_batch_id"] is not None for r in rows):
            raise HTTPException(status_code=409, detail="Range overlaps an existing batch")
        if any(not r["curr_hash"] for r in rows):
            raise HTTPException(status_code=409, detail="Range contains logs without hash links")
        levels = build_levels([r["curr_hash"] for r in rows])
        created = repo.now_iso()
        params = {"r": levels[-1][0], "n": len(rows), "f": rows[0]["seq_id"], "t": rows[-1]["seq_id"],
                  "l": json.dumps(levels), "c": created}
        conn.execute(text("INSERT INTO merkle_batches(root, leaf_count, from_seq, to_seq, levels_json, created_at)"
                          " VALUES (:r,:n,:f,:t,:l,:c)"), params)
        batch_id = conn.execute(text("SELECT max(batch_id) FROM merkle_batches")).scalar()
        conn.execute(text("UPDATE security_logs SET merkle_batch_id=:b WHERE seq_id BETWEEN :f AND :t"),
                     {"b": batch_id, "f": params["f"], "t": params["t"]})
    return {"batch_id": batch_id, "root": params["r"], "leaf_count": params["n"], "from_seq": params["f"],
            "to_seq": params["t"], "created_at": created}


def get_batch(conn, batch_id: int) -> dict:
    r = conn.execute(text("SELECT * FROM merkle_batches WHERE batch_id=:b"), {"b": batch_id}).first()
    if not r:
        raise HTTPException(status_code=404, detail=f"Merkle batch {batch_id} not found")
    d = dict(r._mapping)
    d["levels"] = json.loads(d.pop("levels_json"))
    a = conn.execute(text("SELECT tx_hash, explorer_url, mode FROM blockchain_anchors WHERE batch_id=:b"),
                     {"b": batch_id}).first()
    d.update({"anchored": a is not None, "anchor_tx_hash": a[0] if a else None,
              "anchor_explorer_url": a[1] if a else None, "anchor_mode": a[2] if a else None})
    return d


@router.post("/build", dependencies=[Jwt])
def post_build(request: Request, body: RangeIn | None = None) -> dict:
    body = body or RangeIn()
    return build_batch(ctx(request).engine, body.from_seq, body.to_seq)


@router.get("/batches", dependencies=[Jwt])
def list_batches(request: Request) -> dict:
    with ctx(request).engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT b.batch_id, b.root, b.leaf_count, b.from_seq, b.to_seq, b.created_at, a.tx_hash, a.mode"
            " FROM merkle_batches b LEFT JOIN blockchain_anchors a ON a.batch_id=b.batch_id ORDER BY b.batch_id DESC"))
        return {"items": [dict(r._mapping) for r in rows]}


@router.get("/{batch_id}", dependencies=[Jwt])
def get_merkle(batch_id: int, request: Request) -> dict:
    with ctx(request).engine.connect() as conn:
        return get_batch(conn, batch_id)


@router.get("/{batch_id}/proof/{seq_id}", dependencies=[Jwt])
def get_proof(batch_id: int, seq_id: int, request: Request) -> dict:
    with ctx(request).engine.connect() as conn:
        b = get_batch(conn, batch_id)
        log = repo.get_log(conn, seq_id)
    if not (b["from_seq"] <= seq_id <= b["to_seq"]) or not log:
        raise HTTPException(status_code=404, detail=f"seq_id {seq_id} not in batch {batch_id}")
    index = seq_id - b["from_seq"]
    return {"batch_id": batch_id, "seq_id": seq_id, "leaf": log["curr_hash"], "leaf_index": index,
            "proof": inclusion_proof(b["levels"], index), "root": b["root"]}
