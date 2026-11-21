"""Per-user app API (signed-in users): POST/GET /logs, GET /verify, POST /merkle/build, GET /merkle/roots,
POST /anchor, GET /anchors, POST /anchors/{anchor_id}/verify.

Each user has an independent hash chain in the tables logs / merkle_roots / anchors. The user is ALWAYS the one
from the verified bearer token (request bodies never carry a user id). The shared SOC chain written by the
Windows agent stays under /api/... (POST /api/logs/ingest etc.).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.api.auth import ctx, require_jwt
from backend.app import user_chain
from backend.app.anchor_service import ServiceError

router = APIRouter(tags=["app (per-user)"])


def current_user(user: dict = Depends(require_jwt)) -> str:
    return str(user.get("user_id"))


def _run(fn, *a, **k):
    try:
        return fn(*a, **k)
    except ServiceError as exc:
        return JSONResponse(status_code=exc.status, content={"detail": exc.detail, **exc.extra})


class LogIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)


class AnchorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    merkle_root_id: Optional[str] = Field(default=None, max_length=64)


@router.post("/logs", status_code=201)
def post_log(body: LogIn, request: Request, user_id: str = Depends(current_user)):
    """Append a log to YOUR chain: next seq, prev_hash = your previous hash, hash = SHA-256(prev || content)."""
    return _run(user_chain.append_log, ctx(request), user_id, body.message)


@router.get("/logs")
def get_logs(request: Request, user_id: str = Depends(current_user),
             page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500)):
    """Your logs, newest first."""
    return _run(user_chain.list_logs, ctx(request), user_id, page, page_size)


@router.get("/verify")
def verify(request: Request, user_id: str = Depends(current_user)):
    """Recompute every hash and link of your chain. result PASS/FAIL, checked_count, issues (modified/missing/reordered)."""
    return _run(user_chain.verify_user_chain, ctx(request), user_id)


@router.post("/merkle/build", status_code=201)
def merkle_build(request: Request, user_id: str = Depends(current_user)):
    """Build and store a Merkle root over your logs added since your last root (400 if there are none)."""
    return _run(user_chain.build_root, ctx(request), user_id)


@router.get("/merkle/roots")
def merkle_roots(request: Request, user_id: str = Depends(current_user)):
    return _run(user_chain.list_roots, ctx(request), user_id)


@router.post("/anchor")
def anchor(request: Request, body: AnchorIn | None = None, user_id: str = Depends(current_user)):
    """Anchor your newest un-anchored Merkle root (or `merkle_root_id`) on Quai Orchard Cyprus-1.

    200 confirmed (tx_hash saved) · 202 pending (sent, no receipt yet) · 400 nothing to anchor · 409 already
    anchored / in progress · 503 Quai not configured or unreachable (the real error is returned).
    """
    return _run(user_chain.anchor_root, ctx(request), user_id, body.merkle_root_id if body else None)


@router.get("/anchors")
def anchors(request: Request, user_id: str = Depends(current_user)):
    return _run(user_chain.list_anchors, ctx(request), user_id)


@router.post("/anchors/{anchor_id}/verify")
def verify_anchor(anchor_id: str, request: Request, user_id: str = Depends(current_user)):
    """Read the root back from the contract and compare it with the stored root and the root recomputed from your logs."""
    return _run(user_chain.verify_anchor, ctx(request), user_id, anchor_id)
