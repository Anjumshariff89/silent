"""Application context shared by all routes (settings, DB engine, WebSocket hub, alerter, chain lock)."""
from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from typing import Any

import anyio
from fastapi import WebSocket
from sqlalchemy.engine import Engine

from backend.app.config import Settings
from backend.integrations.alerts import Alerter


class LiveHub:
    """Fan-out of live events to /ws/live subscribers."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def broadcast(self, msg_type: str, data: dict) -> None:
        payload = json.dumps({"type": msg_type, "data": data}, default=str)
        for ws in list(self.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect(ws)

    def broadcast_from_thread(self, msg_type: str, data: dict) -> None:
        """Call from sync (threadpool) endpoints."""
        if not self.clients:
            return
        try:
            anyio.from_thread.run(self.broadcast, msg_type, data)
        except RuntimeError:  # not in a worker thread (e.g. direct call in tests)
            try:
                asyncio.get_running_loop().create_task(self.broadcast(msg_type, data))
            except RuntimeError:
                pass


@dataclass
class AppContext:
    settings: Settings
    engine: Engine
    alerter: Alerter
    anchorer: Any = None  # SimulatedChain | Web3Anchorer
    hub: LiveHub = field(default_factory=LiveHub)
    chain_lock: threading.Lock = field(default_factory=threading.Lock)
