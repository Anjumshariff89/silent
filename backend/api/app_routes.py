"""Short routes for the dashboard app flow: POST/GET /logs, GET /verify, POST /merkle/build, POST /anchor, GET /anchors.

They call the same code as the /api/... routes (one hash chain, one Merkle builder, one anchoring path), so
behaviour and data are identical; only the URLs are shorter. All are authenticated; POST /logs also accepts the
agent X-API-Key.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from backend.api.auth import ApiKeyOrJwt, Jwt, ctx
from backend.api.core_routes import get_logs, ingest
from backend.api.merkle_routes import build_batch
from backend.api.schemas import IngestIn, RangeIn
from backend.app.anchor_service import ServiceError, anchor_batch
from backend.app.integrity_service import run_chain_verification

router = APIRouter(tags=["app"])


@router.post("/logs", dependencies=[ApiKeyOrJwt])
def post_logs(body: IngestIn, request: Request) -> dict:
    """Ingest one log: validated, given the next seq_id and SHA-256 chained (same as /api/logs/ingest)."""
    return ingest(body, request)


@router.get("/logs", dependencies=[Jwt])
def list_logs(request: Request, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
              q: Optional[str] = Query(None, max_length=200)) -> dict:
    return get_logs(request, page=page, page_size=page_size, q=q, event_id=None, event_type=None, severity=None,
                    agent_id=None, source_ip=None, time_from=None, time_to=None, sort="desc")


@router.get("/verify", dependencies=[Jwt])
def verify_chain(request: Request) -> dict:
    """Recompute every hash link of the live chain; tampering yields result FAIL, issues and incidents."""
    return run_chain_verification(ctx(request))


@router.post("/merkle/build", dependencies=[Jwt])
def merkle_build(request: Request, body: RangeIn | None = None) -> dict:
    body = body or RangeIn()
    return build_batch(ctx(request).engine, body.from_seq, body.to_seq)


class AnchorLatestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: Optional[int] = Field(default=None, ge=1)


@router.post("/anchor", dependencies=[Jwt])
def anchor_latest(request: Request, body: AnchorLatestIn | None = None) -> dict:
    """Anchor a Merkle root on Quai (default: the newest batch not anchored yet) and store the tx hash."""
    c = ctx(request)
    batch_id = body.batch_id if body and body.batch_id else None
    if batch_id is None:
        with c.engine.connect() as conn:
            batch_id = conn.execute(text(
                "SELECT b.batch_id FROM merkle_batches b LEFT JOIN blockchain_anchors a ON a.batch_id=b.batch_id"
                " WHERE a.batch_id IS NULL ORDER BY b.batch_id DESC LIMIT 1")).scalar()
        if batch_id is None:
            raise HTTPException(status_code=400, detail="No un-anchored Merkle batch: build one first (POST /merkle/build)")
    try:
        return anchor_batch(c, int(batch_id))
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.get("/anchors", dependencies=[Jwt])
def list_anchors(request: Request) -> dict:
    """Stored anchors. A row exists only after the transaction was mined with status 1, hence status 'confirmed'."""
    with ctx(request).engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT a.id, a.batch_id AS merkle_root_id, b.root, b.leaf_count, a.tx_hash, a.chain_id, a.block_number,"
            " a.block_timestamp, a.contract_address, a.explorer_url, a.mode, a.created_at"
            " FROM blockchain_anchors a JOIN merkle_batches b ON b.batch_id=a.batch_id ORDER BY a.id DESC"))
        return {"items": [{**dict(r._mapping), "status": "confirmed"} for r in rows]}
