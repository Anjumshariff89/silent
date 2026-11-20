"""Background heartbeat monitor: flips agents to offline and raises heartbeat_timeout incidents."""
from __future__ import annotations

import asyncio
import logging

import anyio

from backend.app.context import AppContext
from backend.database import repo

log = logging.getLogger("lace.monitor")


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
    while True:
        try:
            for ev in await anyio.to_thread.run_sync(check_agents_once, c):
                await c.hub.broadcast("agent_status", {"agent_id": ev["agent"]["agent_id"], "status": "offline"})
                await c.hub.broadcast("incident", ev["incident"])
        except Exception as exc:  # keep monitoring
            log.warning("monitor error: %s", type(exc).__name__)
        await asyncio.sleep(c.settings.monitor_interval_s)
