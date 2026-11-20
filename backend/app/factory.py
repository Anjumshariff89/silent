"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import Settings, load_settings
from backend.app.context import AppContext
from backend.app.monitor import monitor_loop
from backend.database.db import apply_schema, make_engine
from backend.integrations.alerts import Alerter

VERSION = "0.1.0"


def create_app(settings: Settings | None = None, run_monitor: bool = True) -> FastAPI:
    settings = settings or load_settings()
    engine = make_engine(settings.database_url)
    apply_schema(engine)
    ctx = AppContext(settings=settings, engine=engine,
                     alerter=Alerter(settings.telegram_bot_token, settings.telegram_chat_id))

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
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                       allow_credentials=False, allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type", "X-API-Key"])

    from backend.api import auth, core_routes
    app.include_router(auth.router)
    app.include_router(core_routes.router)
    for mod in ("integrity_routes", "merkle_routes", "blockchain_routes", "evidence_routes", "demo_routes"):
        try:  # routers added by later steps
            m = __import__(f"backend.api.{mod}", fromlist=["router"])
            app.include_router(m.router)
        except ModuleNotFoundError:
            pass
    return app
