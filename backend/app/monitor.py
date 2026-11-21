"""Background monitor: flips agents to offline (heartbeat_timeout incidents) and sends the ingestion summary."""
from __future__ import annotations

import asyncio
import logging
import time

import anyio

from backend.app.context import AppContext
from backend.database import repo

log = logging.getLogger("lace.monitor")
INGEST_SUMMARY_SECONDS = 60.0


def send_ingest_summary(c: AppContext) -> str | None:
    """One Telegram message per interval with the number of logs ingested (never one message per log)."""
    n = c.take_ingest_count()
    if not n:
        return None
    text_ = f"Ingestion summary: {n} log(s) ingested and SHA-256 chained in the last {int(INGEST_SUMMARY_SECONDS)} s"
    c.alerter.send(text_)
    return text_


def check_agents_once(c: AppContext) -> list[dict]:
    """Return newly-offline agents (each gets one incident + alert until it heartbeats again)."""
    s = c.settings
    events = []
    with c.engine.begin() as conn:
        for a in repo.list_agents(conn, s.heartbeat_online_s, s.heartbeat_offline_s):
            if a["status"] == "offline" and a["last_heartbeat"] and not a["offline_alerted"]:
                desc = (f"Agent {a['agent_id']} missed heartbeats: last seen {a['seconds_since_heartbeat']} s ago "
                        f"(offline threshold {s.heartbeat_offline_s:.0f} s)")
                channel, sent = c.alerter.send(desc)
                inc = repo.create_incident(conn, type="heartbeat_timeout", severity="warning", agent_id=a["agent_id"],
                                           description=desc, alert_channel=channel, alert_sent=sent)
                repo.mark_offline_alerted(conn, a["agent_id"])
                events.append({"agent": {**a, "status": "offline"}, "incident": inc})
    return events


async def monitor_loop(c: AppContext) -> None:
    last_summary = time.monotonic()
    while True:
        try:
            for ev in await anyio.to_thread.run_sync(check_agents_once, c):
                await c.hub.broadcast("agent_status", {"agent_id": ev["agent"]["agent_id"], "status": "offline"})
                await c.hub.broadcast("incident", ev["incident"])
        except Exception as exc:  # keep monitoring
            log.warning("monitor error: %s", type(exc).__name__)
        if time.monotonic() - last_summary >= INGEST_SUMMARY_SECONDS:
            last_summary = time.monotonic()
            try:
                await anyio.to_thread.run_sync(send_ingest_summary, c)
            except Exception as exc:  # Telegram problems never stop monitoring
                log.warning("ingest summary error: %s", type(exc).__name__)
        await asyncio.sleep(c.settings.monitor_interval_s)
