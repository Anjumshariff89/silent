"""Data-access functions. Every query uses bound parameters."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.crypto.hashing import GENESIS_PREV_HASH, compute_log_hash

LOG_COLUMNS = ("seq_id, agent_id, event_id, event_type, severity, source_host, username, source_ip, "
               "message, event_time, received_at, merkle_batch_id")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _row(r) -> dict:
    return dict(r._mapping)


# ----------------------------------------------------------------------------- agents / heartbeats
def ensure_agent(conn: Connection, agent_id: str, hostname: str = "unknown", version: str = "0.0.0",
                 mode: str = "simulator") -> None:
    # Atomic upsert-if-absent: first heartbeat and first event can arrive concurrently.
    conn.execute(text("INSERT INTO agents(agent_id, hostname, agent_version, collector_mode, registered_at)"
                      " VALUES (:a, :h, :v, :m, :t) ON CONFLICT (agent_id) DO NOTHING"),
                 {"a": agent_id, "h": hostname, "v": version, "m": mode, "t": now_iso()})


def record_heartbeat(conn: Connection, hb: dict) -> str:
    received = now_iso()
    ensure_agent(conn, hb["agent_id"], hb["hostname"], hb["agent_version"], hb["collector_mode"])
    conn.execute(text("UPDATE agents SET hostname=:h, agent_version=:v, collector_mode=:m, last_heartbeat=:t,"
                      " offline_alerted=0 WHERE agent_id=:a"),
                 {"h": hb["hostname"], "v": hb["agent_version"], "m": hb["collector_mode"], "t": received,
                  "a": hb["agent_id"]})
    conn.execute(text("INSERT INTO heartbeats(agent_id, collector_mode, sent_at, received_at) VALUES (:a,:m,:s,:t)"),
                 {"a": hb["agent_id"], "m": hb["collector_mode"], "s": hb.get("sent_at"), "t": received})
    return received


def list_heartbeats(conn: Connection, agent_id: str | None, limit: int) -> list[dict]:
    sql = "SELECT id, agent_id, collector_mode, sent_at, received_at FROM heartbeats"
    params: dict[str, Any] = {"l": limit}
    if agent_id:
        sql += " WHERE agent_id=:a"
        params["a"] = agent_id
    sql += " ORDER BY id DESC LIMIT :l"
    return [_row(r) for r in conn.execute(text(sql), params)]


def agent_status(last_heartbeat: str | None, online_s: float, offline_s: float) -> tuple[str, float | None]:
    if not last_heartbeat:
        return "offline", None
    age = (datetime.now(timezone.utc) - parse_iso(last_heartbeat)).total_seconds()
    if age <= online_s:
        return "online", round(age, 1)
    if age <= offline_s:
        return "delayed", round(age, 1)
    return "offline", round(age, 1)


def list_agents(conn: Connection, online_s: float, offline_s: float) -> list[dict]:
    out = []
    for r in conn.execute(text("SELECT * FROM agents ORDER BY agent_id")):
        d = _row(r)
        status, age = agent_status(d["last_heartbeat"], online_s, offline_s)
        out.append({"agent_id": d["agent_id"], "hostname": d["hostname"], "agent_version": d["agent_version"],
                    "collector_mode": d["collector_mode"], "last_heartbeat": d["last_heartbeat"],
                    "seconds_since_heartbeat": age, "status": status, "offline_alerted": bool(d["offline_alerted"])})
    return out


def mark_offline_alerted(conn: Connection, agent_id: str) -> None:
    conn.execute(text("UPDATE agents SET offline_alerted=1 WHERE agent_id=:a"), {"a": agent_id})


# ----------------------------------------------------------------------------- logs + hash chain
def chain_head(conn: Connection) -> tuple[int, str]:
    r = conn.execute(text("SELECT h.seq_id, h.curr_hash FROM hash_chain h ORDER BY h.seq_id DESC LIMIT 1")).first()
    return (r[0], r[1]) if r else (0, GENESIS_PREV_HASH)


def insert_log(conn: Connection, event: dict) -> dict:
    """Append one log + its hash link. Caller must hold the chain lock (sequential seq_id)."""
    ensure_agent(conn, event["agent_id"], event.get("source_host") or "unknown")
    last_seq, prev_hash = chain_head(conn)
    seq_id = last_seq + 1
    log = {**event, "received_at": now_iso()}
    curr_hash = compute_log_hash(prev_hash, log)
    conn.execute(text(
        "INSERT INTO security_logs(seq_id, agent_id, event_id, event_type, severity, source_host, username,"
        " source_ip, message, event_time, received_at)"
        " VALUES (:seq_id, :agent_id, :event_id, :event_type, :severity, :source_host, :username, :source_ip,"
        " :message, :event_time, :received_at)"), {"seq_id": seq_id, **log})
    conn.execute(text("INSERT INTO hash_chain(seq_id, prev_hash, curr_hash, created_at) VALUES (:s,:p,:c,:t)"),
                 {"s": seq_id, "p": prev_hash, "c": curr_hash, "t": log["received_at"]})
    return {"seq_id": seq_id, **log, "prev_hash": prev_hash, "curr_hash": curr_hash, "merkle_batch_id": None}


JOINED = (f"SELECT l.{LOG_COLUMNS.replace(', ', ', l.')}, h.prev_hash, h.curr_hash "
          "FROM security_logs l LEFT JOIN hash_chain h ON h.seq_id = l.seq_id")


def fetch_chain_rows(conn: Connection, from_seq: int | None = None, to_seq: int | None = None) -> list[dict]:
    sql, params, where = JOINED, {}, []
    if from_seq is not None:
        where.append("l.seq_id >= :f")
        params["f"] = from_seq
    if to_seq is not None:
        where.append("l.seq_id <= :t")
        params["t"] = to_seq
    if where:
        sql += " WHERE " + " AND ".join(where)
    return [_row(r) for r in conn.execute(text(sql + " ORDER BY l.seq_id ASC"), params)]


def get_log(conn: Connection, seq_id: int) -> dict | None:
    r = conn.execute(text(JOINED + " WHERE l.seq_id=:s"), {"s": seq_id}).first()
    return _row(r) if r else None


def search_logs(conn: Connection, *, page: int, page_size: int, q: str | None = None, event_id: int | None = None,
                event_type: str | None = None, severity: str | None = None, agent_id: str | None = None,
                source_ip: str | None = None, time_from: str | None = None, time_to: str | None = None,
                sort: str = "desc") -> tuple[list[dict], int]:
    where, params = [], {}
    for col, val in (("event_id", event_id), ("event_type", event_type), ("severity", severity),
                     ("agent_id", agent_id), ("source_ip", source_ip)):
        if val is not None:
            where.append(f"l.{col} = :{col}")  # column names are fixed literals, values are bound
            params[col] = val
    if q:
        where.append("(lower(l.message) LIKE :q OR lower(coalesce(l.username,'')) LIKE :q"
                     " OR lower(l.source_host) LIKE :q)")
        params["q"] = f"%{q.lower()}%"
    if time_from:
        where.append("l.event_time >= :tf")
        params["tf"] = time_from
    if time_to:
        where.append("l.event_time <= :tt")
        params["tt"] = time_to
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(text("SELECT count(*) FROM security_logs l" + clause), params).scalar() or 0
    order = "ASC" if sort == "asc" else "DESC"
    params.update({"lim": page_size, "off": (page - 1) * page_size})
    rows = conn.execute(text(f"{JOINED}{clause} ORDER BY l.seq_id {order} LIMIT :lim OFFSET :off"), params)
    return [_row(r) for r in rows], int(total)


def count_logs(conn: Connection) -> int:
    return int(conn.execute(text("SELECT count(*) FROM security_logs")).scalar() or 0)


# ----------------------------------------------------------------------------- incidents / verification
def create_incident(conn: Connection, *, type: str, description: str, severity: str = "critical",
                    seq_id: int | None = None, agent_id: str | None = None, batch_id: int | None = None,
                    verification_id: int | None = None, target: str = "live", alert_channel: str | None = None,
                    alert_sent: bool = False) -> dict:
    created = now_iso()
    params = {"type": type, "sev": severity, "seq": seq_id, "ag": agent_id, "b": batch_id, "v": verification_id,
              "tg": target, "d": description, "ch": alert_channel, "s": int(alert_sent), "t": created}
    conn.execute(text(
        "INSERT INTO incidents(type, severity, seq_id, agent_id, batch_id, verification_id, target, description,"
        " alert_channel, alert_sent, created_at) VALUES (:type,:sev,:seq,:ag,:b,:v,:tg,:d,:ch,:s,:t)"), params)
    new_id = conn.execute(text("SELECT max(id) FROM incidents")).scalar()
    return get_incident(conn, new_id)


def get_incident(conn: Connection, incident_id: int) -> dict:
    d = _row(conn.execute(text("SELECT * FROM incidents WHERE id=:i"), {"i": incident_id}).first())
    d["alert_sent"] = bool(d["alert_sent"])
    return d


def list_incidents(conn: Connection, *, status: str | None, type: str | None, page: int, page_size: int,
                   target: str | None = None) -> tuple[list[dict], int]:
    where, params = [], {}
    for col, val in (("status", status), ("type", type), ("target", target)):
        if val:
            where.append(f"{col} = :{col}")
            params[col] = val
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(text("SELECT count(*) FROM incidents" + clause), params).scalar() or 0
    params.update({"lim": page_size, "off": (page - 1) * page_size})
    rows = conn.execute(text(f"SELECT * FROM incidents{clause} ORDER BY id DESC LIMIT :lim OFFSET :off"), params)
    items = []
    for r in rows:
        d = _row(r)
        d["alert_sent"] = bool(d["alert_sent"])
        items.append(d)
    return items, int(total)


def resolve_incidents(conn: Connection, target: str | None = None) -> int:
    sql, params = "UPDATE incidents SET status='resolved' WHERE status='open'", {}
    if target:
        sql += " AND target=:t"
        params["t"] = target
    return conn.execute(text(sql), params).rowcount


def record_verification(conn: Connection, *, kind: str, result: str, checked_count: int, issues: list[dict],
                        batch_id: int | None = None, target: str = "live") -> dict:
    ts = now_iso()
    conn.execute(text("INSERT INTO verification_results(kind, target, result, checked_count, batch_id, issues_json,"
                      " verified_at) VALUES (:k,:tg,:r,:c,:b,:i,:t)"),
                 {"k": kind, "tg": target, "r": result, "c": checked_count, "b": batch_id,
                  "i": json.dumps(issues), "t": ts})
    vid = conn.execute(text("SELECT max(id) FROM verification_results")).scalar()
    return {"id": vid, "verified_at": ts}


def last_verification(conn: Connection, kind: str = "chain") -> dict | None:
    r = conn.execute(text("SELECT * FROM verification_results WHERE kind=:k ORDER BY id DESC LIMIT 1"),
                     {"k": kind}).first()
    return _row(r) if r else None
