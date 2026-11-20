"""Log agent: collects events and APPENDS them to the server. Heartbeat every 10 seconds.

Append-only by design: the agent only ever issues HTTP POST to /api/logs/ingest and
/api/heartbeats. There is no update, delete or edit code path (enforced by a test).

Usage (PowerShell):
    .\\.venv\\Scripts\\python.exe -m backend.agent.agent --server https://your-host:8443
"""
from __future__ import annotations

import argparse
import os
import platform
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from backend.agent.collector import make_collector
from backend.app.config import load_settings

AGENT_VERSION = "0.1.0"
HEARTBEAT_INTERVAL_S = 10.0
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def require_https(url: str) -> None:
    """HTTPS is mandatory except for loopback development servers."""
    p = urlparse(url)
    if p.scheme != "https" and p.hostname not in LOOPBACK:
        raise ValueError(f"Refusing to send logs over {p.scheme}:// to non-loopback host {p.hostname}; use https://")


class LogAgent:
    def __init__(self, server: str, api_key: str, agent_id: str, collector, ca_bundle: str | bool = True,
                 heartbeat_interval: float = HEARTBEAT_INTERVAL_S):
        require_https(server)
        self.server = server.rstrip("/")
        self.agent_id = agent_id
        self.collector = collector
        self.heartbeat_interval = heartbeat_interval
        self._stop = threading.Event()
        self.client = httpx.Client(headers={"X-API-Key": api_key}, verify=ca_bundle, timeout=10.0)

    # The ONLY two network operations the agent performs. Both are POST (append).
    def send_event(self, event: dict) -> dict:
        r = self.client.post(f"{self.server}/api/logs/ingest", json={"agent_id": self.agent_id, **event})
        r.raise_for_status()
        return r.json()

    def send_heartbeat(self) -> dict:
        r = self.client.post(f"{self.server}/api/heartbeats", json={
            "agent_id": self.agent_id,
            "hostname": getattr(self.collector, "hostname", platform.node()),
            "agent_version": AGENT_VERSION,
            "collector_mode": self.collector.mode,
            "sent_at": _now(),
        })
        r.raise_for_status()
        return r.json()

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.send_heartbeat()
            except Exception as exc:
                print(f"[agent] heartbeat failed: {type(exc).__name__}")
            self._stop.wait(self.heartbeat_interval)

    def run(self, poll_interval: float = 3.0, max_events: int = 3) -> None:
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        print(f"[agent] {self.agent_id} running, collector={self.collector.mode}, server={self.server}")
        while not self._stop.is_set():
            for ev in self.collector.collect(max_events):
                try:
                    res = self.send_event(ev)
                    print(f"[agent] sent event {ev['event_id']} -> seq_id={res.get('seq_id')}")
                except Exception as exc:
                    print(f"[agent] send failed: {type(exc).__name__}")
            self._stop.wait(poll_interval)

    def stop(self) -> None:
        self._stop.set()


def main() -> None:
    ap = argparse.ArgumentParser(description="Tamper-evident log agent")
    ap.add_argument("--server", default=os.getenv("AGENT_SERVER_URL", "http://127.0.0.1:8000"))
    ap.add_argument("--agent-id", default=os.getenv("AGENT_ID", "agent-win-01"))
    ap.add_argument("--collector", choices=["auto", "windows", "simulator"], default="auto")
    ap.add_argument("--ca-bundle", default=None, help="CA file for a self-signed server certificate")
    ap.add_argument("--poll", type=float, default=3.0)
    args = ap.parse_args()
    settings = load_settings()
    collector = make_collector(args.collector)
    agent = LogAgent(args.server, settings.api_key, args.agent_id, collector, ca_bundle=args.ca_bundle or True)
    try:
        agent.run(poll_interval=args.poll)
    except KeyboardInterrupt:
        agent.stop()


if __name__ == "__main__":
    main()
