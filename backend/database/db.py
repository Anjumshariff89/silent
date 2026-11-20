"""Database access: SQLAlchemy engine for Postgres/Supabase (REAL) or SQLite (SIMULATED fallback).

The schema is applied from schema.sql / schema_postgres.sql (single source of truth), and queries
use SQLAlchemy Core `text()` with bound parameters only (no string formatting = no SQL injection).
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

SCHEMA_DIR = Path(__file__).resolve().parent
TABLES = [
    "agents", "merkle_batches", "security_logs", "hash_chain", "heartbeats",
    "blockchain_anchors", "verification_results", "incidents",
]


def is_sqlite(engine: Engine) -> bool:
    return engine.dialect.name == "sqlite"


def make_engine(database_url: str) -> Engine:
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    if database_url.startswith("sqlite"):
        if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
            Path(database_url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON")
            cur.execute("PRAGMA journal_mode = WAL")
            cur.close()

        return engine
    return create_engine(database_url, pool_pre_ping=True, future=True)


def schema_sql(engine: Engine) -> str:
    name = "schema.sql" if is_sqlite(engine) else "schema_postgres.sql"
    return (SCHEMA_DIR / name).read_text(encoding="utf-8")


def _statements(sql: str) -> list[str]:
    lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def apply_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        for stmt in _statements(schema_sql(engine)):
            conn.execute(text(stmt))


def list_tables(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        if is_sqlite(engine):
            rows = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"))
        else:
            rows = conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"))
        return [r[0] for r in rows]
