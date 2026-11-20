"""Dashboard demo: "Tamper this log". Attacks a SANDBOX COPY of the data, never the live tables."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import Field

from backend.api.auth import Jwt, ctx
from backend.api.schemas import Strict
from backend.app.config import DATA_DIR
from backend.app.integrity_service import run_chain_verification
from backend.crypto.tamper_simulator import fingerprint, make_sandbox, tamper
from backend.database import repo

router = APIRouter(prefix="/api/demo", tags=["demo"])


class TamperIn(Strict):
    seq_id: int = Field(ge=1)
    kind: Literal["modify", "delete", "reorder"] = "modify"


@router.post("/tamper", dependencies=[Jwt])
def demo_tamper(body: TamperIn, request: Request) -> dict:
    c = ctx(request)
    before = fingerprint(c.engine)
    sandbox = make_sandbox(c.engine, DATA_DIR / "tamper_sandbox.db")
    try:
        action = tamper(sandbox, body.kind, body.seq_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result = run_chain_verification(c, source=sandbox, target="sandbox")
    sandbox.dispose()
    return {"attack": action, "sandbox": str((DATA_DIR / "tamper_sandbox.db").name), "verification": result,
            "original_unchanged": fingerprint(c.engine) == before}


@router.post("/reset", dependencies=[Jwt])
def demo_reset(request: Request) -> dict:
    c = ctx(request)
    with c.engine.begin() as conn:
        resolved = repo.resolve_incidents(conn, "sandbox")
    live = run_chain_verification(c)  # re-verify the untouched live chain
    return {"resolved_sandbox_incidents": resolved, "live_verification": live["result"]}
