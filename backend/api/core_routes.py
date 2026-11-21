"""Core endpoints: ingest, logs, heartbeats, agents, health, WebSocket /ws/live."""
from __future__ import annotations

from typing import Literal, Optional

import jwt
from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from backend.api.auth import ApiKey, Jwt, ctx, decode_token
from backend.api.schemas import HeartbeatIn, IngestIn
from backend.app.config import Settings
from backend.database import repo

router = APIRouter()


@router.post("/api/logs/ingest", dependencies=[ApiKey], tags=["logs"])
def ingest(body: IngestIn, request: Request) -> dict:
    c = ctx(request)
    with c.chain_lock, c.engine.begin() as conn:  # lock => strictly sequential seq_id & chain
        log = repo.insert_log(conn, body.to_record())
    c.hub.broadcast_from_thread("log", log)
    return {"status": "accepted", "seq_id": log["seq_id"], "prev_hash": log["prev_hash"],
            "curr_hash": log["curr_hash"], "received_at": log["received_at"]}


@router.get("/api/logs", dependencies=[Jwt], tags=["logs"])
def get_logs(request: Request,
             page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
             q: Optional[str] = Query(None, max_length=200), event_id: Optional[int] = None,
             event_type: Optional[str] = None, severity: Optional[str] = None, agent_id: Optional[str] = None,
             source_ip: Optional[str] = None, time_from: Optional[str] = Query(None, alias="from"),
             time_to: Optional[str] = Query(None, alias="to"), sort: Literal["asc", "desc"] = "desc") -> dict:
    with ctx(request).engine.connect() as conn:
        items, total = repo.search_logs(conn, page=page, page_size=page_size, q=q, event_id=event_id,
                                        event_type=event_type, severity=severity, agent_id=agent_id,
                                        source_ip=source_ip, time_from=time_from, time_to=time_to, sort=sort)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.post("/api/heartbeats", dependencies=[ApiKey], tags=["agents"])
def post_heartbeat(body: HeartbeatIn, request: Request) -> dict:
    c = ctx(request)
    hb = body.model_dump()
    hb["sent_at"] = hb["sent_at"].isoformat() if hb["sent_at"] else None
    with c.engine.begin() as conn:
        received = repo.record_heartbeat(conn, hb)
    c.hub.broadcast_from_thread("heartbeat", {"agent_id": body.agent_id, "received_at": received})
    return {"status": "ok", "agent_id": body.agent_id, "received_at": received}


@router.get("/api/heartbeats", dependencies=[Jwt], tags=["agents"])
def get_heartbeats(request: Request, agent_id: Optional[str] = None, limit: int = Query(100, ge=1, le=1000)) -> dict:
    with ctx(request).engine.connect() as conn:
        return {"items": repo.list_heartbeats(conn, agent_id, limit)}


@router.get("/api/agents", dependencies=[Jwt], tags=["agents"])
def get_agents(request: Request) -> dict:
    s: Settings = ctx(request).settings
    with ctx(request).engine.connect() as conn:
        return {"items": repo.list_agents(conn, s.heartbeat_online_s, s.heartbeat_offline_s)}


@router.get("/health", tags=["health"])
@router.get("/api/health", tags=["health"])
def health(request: Request) -> dict:
    c = ctx(request)
    db = {"status": "ok", "backend": c.engine.dialect.name}
    log_count = None
    try:
        with c.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            log_count = repo.count_logs(conn)
    except Exception as exc:
        db = {"status": "error", "backend": c.engine.dialect.name, "error": type(exc).__name__}
    return {"status": "ok" if db["status"] == "ok" else "degraded", "version": request.app.version,
            "mode": c.settings.mode, "database": db,
            # blockchain badge comes from the anchorer actually in use, not just from which keys are set
            "integrations": {**c.settings.integration_modes(), "blockchain": c.anchorer.mode},
            "dev_api_key_in_use": c.settings.using_dev_api_key, "log_count": log_count, "time": repo.now_iso()}


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket, token: str = ""):
    c = websocket.app.state.ctx
    try:
        decode_token(c.settings.jwt_secret, token)
    except jwt.PyJWTError:
        await websocket.close(code=1008)
        return
    await c.hub.connect(websocket)
    try:
        await websocket.send_text('{"type":"hello","data":{"status":"subscribed"}}')
        while True:
            await websocket.receive_text()  # keepalive / ignore client messages
    except WebSocketDisconnect:
        pass
    finally:
        c.hub.disconnect(websocket)
