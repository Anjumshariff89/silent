"""Step 2: schema applies, 8 tables exist, constraints reject bad data.

SQLite tests always run. Postgres tests run when PG_TEST_URL (superuser URL to a throwaway DB)
is set, and also verify the restricted log_writer role.
"""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from backend.database.db import TABLES, apply_schema, list_tables, make_engine

NOW = "2026-11-20T00:00:00Z"


def _seed_agent(conn):
    conn.execute(text("INSERT INTO agents(agent_id, hostname, registered_at) VALUES ('a1','h1',:t)"), {"t": NOW})


def _insert_log(conn, seq, agent="a1"):
    conn.execute(text(
        "INSERT INTO security_logs(seq_id, agent_id, event_id, event_type, source_host, message, event_time, received_at)"
        " VALUES (:s, :a, 4624, 'logon', 'h1', 'synthetic', :t, :t)"), {"s": seq, "a": agent, "t": NOW})


@pytest.fixture
def sqlite_engine(tmp_path: Path):
    eng = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    apply_schema(eng)
    return eng


def _check_engine(eng):
    assert sorted(t for t in list_tables(eng) if t in TABLES) == sorted(TABLES)
    with eng.begin() as c:
        _seed_agent(c)
        _insert_log(c, 1)
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM security_logs")).scalar() == 1
    with pytest.raises(IntegrityError, match="(?i)unique"):
        with eng.begin() as c:
            _insert_log(c, 1)  # duplicate seq_id
    with pytest.raises(IntegrityError, match="(?i)foreign key"):
        with eng.begin() as c:
            _insert_log(c, 2, agent="no-such-agent")  # bad FK


def test_sqlite_schema_and_constraints(sqlite_engine):
    _check_engine(sqlite_engine)


def test_schema_is_idempotent(sqlite_engine):
    apply_schema(sqlite_engine)  # second run must not fail
    assert len([t for t in list_tables(sqlite_engine) if t in TABLES]) == 8


def test_hash_chain_requires_existing_log(sqlite_engine):
    with pytest.raises(IntegrityError, match="(?i)foreign key"):
        with sqlite_engine.begin() as c:
            c.execute(text("INSERT INTO hash_chain(seq_id, prev_hash, curr_hash, created_at) VALUES (99, :h, :h, :t)"),
                      {"h": "0" * 64, "t": NOW})


PG_URL = os.getenv("PG_TEST_URL")


@pytest.mark.skipif(not PG_URL, reason="PG_TEST_URL not set")
def test_postgres_schema_constraints_and_restricted_role():
    eng = make_engine(PG_URL)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        c.execute(text("DROP ROLE IF EXISTS log_writer"))
    apply_schema(eng)
    _check_engine(eng)
    roles = (Path(__file__).resolve().parents[1] / "backend/database/roles_postgres.sql").read_text()
    with eng.begin() as c:
        c.exec_driver_sql(roles.replace("CHANGE_ME_IN_SQL_EDITOR", "test-only-pw"))
    url = eng.url.set(username="log_writer", password="test-only-pw")
    w = create_engine(url)
    with w.begin() as c:
        _insert_log(c, 50)                                    # INSERT allowed
        assert c.execute(text("SELECT count(*) FROM security_logs")).scalar() == 2  # SELECT allowed
    for stmt in ["UPDATE security_logs SET message='x'", "DELETE FROM security_logs",
                 "TRUNCATE security_logs", "SELECT * FROM incidents"]:
        with pytest.raises(ProgrammingError, match="permission denied"):
            with w.begin() as c:
                c.execute(text(stmt))
    w.dispose()
    eng.dispose()
