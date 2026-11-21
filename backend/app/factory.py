"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path

from backend.app.config import DATA_DIR, Settings, load_settings
from backend.app.context import AppContext
from backend.app.monitor import monitor_loop
from backend.database.db import apply_schema, make_engine
from backend.blockchain.anchor import make_anchorer
from backend.integrations.alerts import Alerter

VERSION = "0.1.0"


def ledger_path(settings: Settings) -> Path:
    """Simulated-chain ledger lives next to a SQLite DB file, else in data/."""
    url = settings.database_url
    if url.startswith("sqlite:///") and ":memory:" not in url:
        db = Path(url[len("sqlite:///"):])
        return db.with_name(db.stem + "_sim_chain.json")
    return DATA_DIR / "sim_chain.json"


def build_context(settings: Settings) -> AppContext:
    engine = make_engine(settings.database_url)
    apply_schema(engine)
    return AppContext(settings=settings, engine=engine,
                      alerter=Alerter(settings.telegram_bot_token, settings.telegram_chat_id),
                      anchorer=make_anchorer(settings, ledger_path(settings)))


log = logging.getLogger("lace.api")


class JSONErrorMiddleware:
    """Turn unexpected exceptions into a JSON 500 INSIDE the CORS layer.

    Without this, Starlette answers unhandled errors from its outermost middleware, before CORS headers are added,
    so the browser blocks the response and the dashboard can only say "Cannot reach the API". The traceback is
    logged server-side; the client gets the error type, never internal details.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)
        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            log.exception("unhandled error on %s %s", scope.get("method"), scope.get("path"))
            if started:
                raise
            body = json.dumps({"detail": f"Internal server error ({type(exc).__name__}); see the backend log"}).encode()
            await send({"type": "http.response.start", "status": 500,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})


def create_app(settings: Settings | None = None, run_monitor: bool = True) -> FastAPI:
    settings = settings or load_settings()
    ctx = build_context(settings)
    engine = ctx.engine

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(monitor_loop(ctx)) if run_monitor else None
        yield
        if task:
            task.cancel()
        engine.dispose()

    app = FastAPI(title="Logs the Attacker Can't Erase", version=VERSION, lifespan=lifespan,
                  description="Tamper-evident security logging. Anchoring proves a commitment is unchanged since "
                              "anchoring; it does not prove that an event happened.")
    app.state.ctx = ctx
    app.add_middleware(JSONErrorMiddleware)  # added first = inner: its 500s still get CORS headers below
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=False, allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type", "X-API-Key"])

    from backend.api import auth, core_routes
    app.include_router(auth.router)
    app.include_router(core_routes.router)
    for mod in ("integrity_routes", "merkle_routes", "blockchain_routes", "evidence_routes", "app_routes"):
        try:  # routers added by later steps
            m = __import__(f"backend.api.{mod}", fromlist=["router"])
            app.include_router(m.router)
        except ModuleNotFoundError:
            pass
    return app
