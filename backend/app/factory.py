"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import contextlib

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
