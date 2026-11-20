"""Blockchain anchoring and proof verification endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from backend.api.auth import Jwt, ctx
from backend.api.schemas import Strict
from backend.app.anchor_service import ServiceError, anchor_batch, blockchain_status, verify_batch

router = APIRouter(tags=["blockchain"])


class AnchorIn(Strict):
    batch_id: int = Field(ge=1)


class ProofVerifyIn(Strict):
    batch_id: int = Field(ge=1)
    seq_id: Optional[int] = Field(default=None, ge=1)


def _call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ServiceError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.post("/api/blockchain/anchor", dependencies=[Jwt])
def post_anchor(body: AnchorIn, request: Request) -> dict:
    return _call(anchor_batch, ctx(request), body.batch_id)


@router.get("/api/blockchain/status", dependencies=[Jwt])
def get_status(request: Request) -> dict:
    return blockchain_status(ctx(request))


@router.post("/api/proof/verify", dependencies=[Jwt])
def post_proof_verify(body: ProofVerifyIn, request: Request) -> dict:
    return _call(verify_batch, ctx(request), body.batch_id, body.seq_id)
