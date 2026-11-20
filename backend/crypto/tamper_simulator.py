"""Tamper simulator. Works ONLY on a COPY of the data.

`make_sandbox()` copies logs + hash links from the source engine into a brand-new SQLite file
(or in-memory DB). All tampering SQL runs against that sandbox engine; the source is opened
read-only (SELECT only). Synthetic data only.

CLI:  python -m backend.crypto.tamper_simulator --kind modify --seq 3
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.database import repo
from backend.database.db import apply_schema, make_engine

KINDS = ("modify", "delete", "reorder")


def fingerprint(engine: Engine) -> str:
    """SHA-256 over every log + hash row: proves the original was not changed."""
    with engine.connect() as conn:
        rows = repo.fetch_chain_rows(conn)
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def make_sandbox(source: Engine, path: str | Path | None = None) -> Engine:
    url = f"sqlite:///{Path(path).as_posix()}" if path else "sqlite:///:memory:"
    if path and Path(path).exists():
        Path(path).unlink()
    sandbox = make_engine(url)
    apply_schema(sandbox)
    with source.connect() as src:  # read-only access to the source
        agents = [dict(r._mapping) for r in src.execute(text("SELECT * FROM agents"))]
        rows = repo.fetch_chain_rows(src)
    with sandbox.begin() as dst:
        for a in agents:
            dst.execute(text("INSERT INTO agents(agent_id, hostname, agent_version, collector_mode, registered_at,"
                             " last_heartbeat, offline_alerted) VALUES (:agent_id,:hostname,:agent_version,"
                             ":collector_mode,:registered_at,:last_heartbeat,:offline_alerted)"), a)
        for r in rows:
            dst.execute(text("INSERT INTO security_logs(seq_id, agent_id, event_id, event_type, severity, source_host,"
                             " username, source_ip, message, event_time, received_at) VALUES (:seq_id,:agent_id,"
                             ":event_id,:event_type,:severity,:source_host,:username,:source_ip,:message,:event_time,"
                             ":received_at)"), r)
            if r["curr_hash"]:
                dst.execute(text("INSERT INTO hash_chain(seq_id, prev_hash, curr_hash, created_at)"
                                 " VALUES (:seq_id,:prev_hash,:curr_hash,:received_at)"), r)
    return sandbox


def tamper(sandbox: Engine, kind: str, seq_id: int) -> str:
    """Apply one attack to the SANDBOX. Returns a description of what the 'attacker' did."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    with sandbox.begin() as conn:
        if not conn.execute(text("SELECT 1 FROM security_logs WHERE seq_id=:s"), {"s": seq_id}).first():
            raise ValueError(f"seq_id {seq_id} not found")
        if kind == "modify":
            conn.execute(text("UPDATE security_logs SET username='attacker', message=message || ' [EDITED]'"
                              " WHERE seq_id=:s"), {"s": seq_id})
            return f"modified username/message of seq {seq_id}"
        if kind == "delete":
            conn.execute(text("DELETE FROM hash_chain WHERE seq_id=:s"), {"s": seq_id})
            conn.execute(text("DELETE FROM security_logs WHERE seq_id=:s"), {"s": seq_id})
            return f"deleted seq {seq_id} (log + hash link)"
        # reorder: swap the full rows (content + hash links) of seq_id and seq_id+1
        other = seq_id + 1
        if not conn.execute(text("SELECT 1 FROM security_logs WHERE seq_id=:s"), {"s": other}).first():
            raise ValueError(f"reorder needs seq {other} to exist")
        conn.execute(text("PRAGMA defer_foreign_keys = ON"))
        for table in ("hash_chain", "security_logs"):
            conn.execute(text(f"UPDATE {table} SET seq_id = 2147483000 WHERE seq_id = :a"), {"a": seq_id})
            conn.execute(text(f"UPDATE {table} SET seq_id = :a WHERE seq_id = :b"), {"a": seq_id, "b": other})
            conn.execute(text(f"UPDATE {table} SET seq_id = :b WHERE seq_id = 2147483000"), {"b": other})
        return f"swapped positions of seq {seq_id} and seq {other}"


def main() -> None:  # pragma: no cover - CLI wrapper
    from backend.app.config import DATA_DIR, load_settings
    from backend.crypto.verifier import verify_chain

    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=KINDS, required=True)
    ap.add_argument("--seq", type=int, required=True)
    args = ap.parse_args()
    src = make_engine(load_settings().database_url)
    before = fingerprint(src)
    sb = make_sandbox(src, DATA_DIR / "tamper_sandbox.db")
    print("attack:", tamper(sb, args.kind, args.seq))
    with sb.connect() as conn:
        print(json.dumps(verify_chain(repo.fetch_chain_rows(conn)), indent=2))
    print("original unchanged:", fingerprint(src) == before)


if __name__ == "__main__":
    main()
