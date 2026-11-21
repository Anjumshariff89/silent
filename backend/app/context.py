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
    anchorer: Any = None  # QuaiServiceAnchorer (REAL) | UnconfiguredAnchorer (no Quai keys)
    hub: LiveHub = field(default_factory=LiveHub)
    chain_lock: threading.Lock = field(default_factory=threading.Lock)
    # Telegram ingestion summary (one message per interval, never one per log) and duplicate-alert suppression.
    ingest_count: int = 0
    _stats_lock: threading.Lock = field(default_factory=threading.Lock)
    _alerted: set = field(default_factory=set)

    def note_ingest(self, n: int = 1) -> None:
        with self._stats_lock:
            self.ingest_count += n

    def take_ingest_count(self) -> int:
        with self._stats_lock:
            n, self.ingest_count = self.ingest_count, 0
            return n

    def alert_once(self, key: str, text: str) -> bool:
        """Send an alert once per key for the lifetime of this process (e.g. one per detected tamper)."""
        with self._stats_lock:
            if key in self._alerted:
                return False
            self._alerted.add(key)
        self.alerter.send(text)
        return True
