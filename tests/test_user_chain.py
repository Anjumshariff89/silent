"""Per-user chains (tables logs / merkle_roots / anchors) behind POST/GET /logs, /verify, /merkle/build, /anchor,
/anchors, /anchors/{id}/verify: hashing, ownership isolation, tamper detection, Merkle, anchoring outcomes,
Telegram events, local mode, env aliases, quai_service retries, and Postgres RLS."""
import os
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.factory import create_app
from backend.blockchain.quai_service import (AlreadyAnchored, AnchorError, AnchorPending, QuaiServiceAnchorer,
                                             UnconfiguredAnchorer)
from backend.crypto.hashing import GENESIS_PREV_HASH, compute_user_log_hash
from backend.merkle.tree import merkle_root
from tests.conftest import make_settings, with_fake_chain
from tests.test_supabase_auth import SUPA_SECRET, SUPA_URL, USER_ID, bearer, supa_token

ROOT = Path(__file__).resolve().parents[1]
OTHER_ID = str(uuid.uuid4())
A = bearer(supa_token())
B = bearer(supa_token(sub=OTHER_ID, email="other@example.test"))


@pytest.fixture
def app(tmp_path):
    s = make_settings(tmp_path, supabase_url=SUPA_URL, supabase_jwt_secret=SUPA_SECRET)
    return with_fake_chain(create_app(s, run_monitor=False), tmp_path)


@pytest.fixture
def c(app):
    with TestClient(app) as client:
        yield client


def add(c, msg, h=A):
    r = c.post("/logs", json={"message": msg}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def db(app, sql, **p):
    with app.state.ctx.engine.begin() as conn:
        return conn.execute(text(sql), p)


# --------------------------------------------------------------------- Test 4: ingestion + hashing
def test_logs_are_sha256_chained_per_user_with_correct_prev_links(c):
    rows = [add(c, f"event {i}") for i in range(3)]
    assert [r["seq"] for r in rows] == [1, 2, 3]
    assert rows[0]["prev_hash"] == GENESIS_PREV_HASH
    for prev, cur in zip(rows, rows[1:]):
        assert cur["prev_hash"] == prev["hash"]
    for r in rows:
        assert r["user_id"] == USER_ID
        assert r["hash"] == compute_user_log_hash(r["prev_hash"], r)  # independent recomputation
    other = add(c, "first log of user B", B)
    assert other["seq"] == 1 and other["prev_hash"] == GENESIS_PREV_HASH  # B has an independent chain


def test_log_input_is_validated_and_body_cannot_choose_the_user(c):
    assert c.post("/logs", json={"message": ""}, headers=A).status_code == 422
    assert c.post("/logs", json={"message": "x" * 4001}, headers=A).status_code == 422
    assert c.post("/logs", json={"message": "x", "user_id": OTHER_ID}, headers=A).status_code == 422
    assert c.post("/logs", json={"message": "x"}).status_code == 401


# --------------------------------------------------------------------- Test 5: isolation
def test_users_cannot_see_or_use_each_others_records(c):
    add(c, "secret of A")
    add(c, "secret of A 2")
    add(c, "note of B", B)
    a_logs, b_logs = c.get("/logs", headers=A).json(), c.get("/logs", headers=B).json()
    assert a_logs["total"] == 2 and b_logs["total"] == 1
    assert all("of A" in i["message"] for i in a_logs["items"]) and b_logs["items"][0]["message"] == "note of B"
    root_a = c.post("/merkle/build", headers=A).json()
    assert root_a["leaf_count"] == 2
    assert c.post("/anchor", json={"merkle_root_id": root_a["id"]}, headers=B).status_code == 404
    anchored = c.post("/anchor", headers=A).json()
    assert c.post(f"/anchors/{anchored['id']}/verify", headers=B).status_code == 404
    assert c.get("/anchors", headers=B).json()["items"] == []
    assert [r["leaf_count"] for r in c.get("/merkle/roots", headers=A).json()["items"]] == [2]
    assert c.get("/merkle/roots", headers=B).json()["items"] == []


# --------------------------------------------------------------------- Tests 6 + 9: verification and tampering
def test_verify_passes_then_detects_modification_deletion_and_moved_rows(app, c):
    for i in range(4):
        add(c, f"event {i}")
    add(c, "B's event", B)
    ok = c.get("/verify", headers=A).json()
    assert ok["result"] == "PASS" and ok["checked_count"] == 4 and ok["issues"] == []

    db(app, "UPDATE logs SET message='attacker was here' WHERE user_id=:u AND seq=2", u=USER_ID)
    v = c.get("/verify", headers=A).json()
    assert v["result"] == "FAIL" and v["issues"][0] == {**v["issues"][0], "type": "modified", "seq_id": 2}
    assert c.get("/verify", headers=B).json()["result"] == "PASS"  # B's chain is unaffected
    sent = [m for m in app.state.ctx.alerter.sent if "Tamper detected in user" in m]
    c.get("/verify", headers=A)
    assert len([m for m in app.state.ctx.alerter.sent if "Tamper detected in user" in m]) == len(sent) == 1  # once

    db(app, "UPDATE logs SET message='event 1' WHERE user_id=:u AND seq=2", u=USER_ID)  # restore
    assert c.get("/verify", headers=A).json()["result"] == "PASS"
    db(app, "DELETE FROM logs WHERE user_id=:u AND seq=3", u=USER_ID)
    assert c.get("/verify", headers=A).json()["issues"][0]["type"] == "missing"


def test_moving_a_row_into_another_users_chain_breaks_its_hash(app, c):
    add(c, "a1")
    add(c, "b1", B)
    db(app, "UPDATE logs SET user_id=:b, seq=2 WHERE user_id=:a AND seq=1", a=USER_ID, b=OTHER_ID)
    v = c.get("/verify", headers=B).json()
    assert v["result"] == "FAIL" and v["issues"][0]["type"] == "modified"


# --------------------------------------------------------------------- Test 7: Merkle
def test_merkle_root_matches_existing_algorithm_and_covers_only_new_logs(c):
    assert c.post("/merkle/build", headers=A).status_code == 400
    rows = [add(c, f"m{i}") for i in range(5)]
    r1 = c.post("/merkle/build", headers=A)
    assert r1.status_code == 201
    r1 = r1.json()
    assert r1["root"] == merkle_root([r["hash"] for r in rows]) and (r1["from_seq"], r1["to_seq"], r1["leaf_count"]) == (1, 5, 5)
    assert c.post("/merkle/build", headers=A).status_code == 400
    more = [add(c, f"n{i}") for i in range(2)]
    r2 = c.post("/merkle/build", headers=A).json()
    assert r2["root"] == merkle_root([r["hash"] for r in more]) and (r2["from_seq"], r2["to_seq"]) == (6, 7)


# --------------------------------------------------------------------- Test 8: anchoring outcomes
def test_anchor_confirms_saves_tx_and_verify_button_checks_chain_and_logs(app, c):
    for i in range(3):
        add(c, f"a{i}")
    root = c.post("/merkle/build", headers=A).json()
    a = c.post("/anchor", headers=A)
    assert a.status_code == 200, a.text
    a = a.json()
    assert a["status"] == "confirmed" and a["tx_hash"].startswith("0x") and a["merkle_root_id"] == root["id"]
    assert a["chain_id"] == 15000 and a["root"] == root["root"]
    assert [x["tx_hash"] for x in c.get("/anchors", headers=A).json()["items"]] == [a["tx_hash"]]
    assert any("Quai anchor confirmed" in m for m in app.state.ctx.alerter.sent)
    assert c.post("/anchor", headers=A).status_code == 400                       # nothing left to anchor
    assert c.post("/anchor", json={"merkle_root_id": root["id"]}, headers=A).status_code == 409
    v = c.post(f"/anchors/{a['id']}/verify", headers=A).json()
    assert v["result"] == "MATCH" and v["onchain_root"] == v["stored_root"] == v["local_root"] == root["root"]
    db(app, "UPDATE logs SET message='rewritten' WHERE user_id=:u AND seq=2", u=USER_ID)
    v = c.post(f"/anchors/{a['id']}/verify", headers=A).json()
    assert v["result"] == "MISMATCH" and v["local_root"] != v["onchain_root"]


def test_not_configured_returns_503_with_reason_and_stores_nothing(tmp_path):
    s = make_settings(tmp_path, supabase_url=SUPA_URL, supabase_jwt_secret=SUPA_SECRET)
    app = create_app(s, run_monitor=False)
    assert isinstance(app.state.ctx.anchorer, UnconfiguredAnchorer)
    with TestClient(app) as c:
        add(c, "x")
        c.post("/merkle/build", headers=A)
        r = c.post("/anchor", headers=A)
        assert r.status_code == 503 and "not configured" in r.json()["detail"]
        assert c.get("/anchors", headers=A).json()["items"] == []


class Flaky:
    """Configured anchorer whose behaviour per call is scripted (wraps the FakeChain test double)."""
    mode, can_anchor, contract_address, chain_id = "SIMULATED", True, None, 15000

    def __init__(self, inner, script):
        self.inner, self.script = inner, list(script)

    def anchor(self, root, key):
        step = self.script.pop(0) if self.script else "ok"
        if step == "fail":
            raise AnchorError("Quai RPC unreachable: getaddrinfo ENOTFOUND orchard.rpc.quai.network")
        if step == "pending":
            self.inner.anchor(root, key)  # it WAS mined, but the answer was lost
            raise AnchorPending("no answer from the quai-service within the timeout")
        return self.inner.anchor(root, key)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_failed_anchor_is_recorded_alerted_and_can_be_retried(app, c):
    app.state.ctx.anchorer = Flaky(app.state.ctx.anchorer, ["fail", "ok"])
    add(c, "x")
    c.post("/merkle/build", headers=A)
    r = c.post("/anchor", headers=A)
    assert r.status_code == 503 and "ENOTFOUND" in r.json()["detail"]
    assert r.json()["anchor"]["status"] == "failed" and r.json()["anchor"]["tx_hash"] is None
    assert any("Quai anchoring FAILED" in m for m in app.state.ctx.alerter.sent)
    r2 = c.post("/anchor", headers=A)
    assert r2.status_code == 200 and r2.json()["status"] == "confirmed"
    assert r2.json()["id"] == r.json()["anchor"]["id"]                              # same record, no duplicate
    assert len(c.get("/anchors", headers=A).json()["items"]) == 1


def test_pending_anchor_is_recovered_from_the_contract_without_a_second_tx(app, c, monkeypatch):
    app.state.ctx.anchorer = Flaky(app.state.ctx.anchorer, ["pending"])
    add(c, "x")
    c.post("/merkle/build", headers=A)
    r = c.post("/anchor", headers=A)
    assert r.status_code == 202 and r.json()["anchor"]["status"] == "pending"
    assert c.post("/anchor", headers=A).status_code == 409                          # in progress
    import backend.app.user_chain as uc
    from datetime import timedelta
    monkeypatch.setattr(uc, "PENDING_RETRY_AFTER", timedelta(0))
    r2 = c.post("/anchor", headers=A)                                               # AlreadyAnchored -> recovered
    assert r2.status_code == 200 and r2.json()["status"] == "confirmed" and r2.json()["tx_hash"]


def test_on_chain_root_mismatch_is_refused(app, c):
    add(c, "x")
    root = c.post("/merkle/build", headers=A).json()
    from backend.app.user_chain import onchain_id_for
    app.state.ctx.anchorer.anchor("ff" * 32, onchain_id_for(root["id"]))           # someone else used the key
    r = c.post("/anchor", headers=A)
    assert r.status_code == 409 and r.json()["anchor"]["status"] == "failed"


# --------------------------------------------------------------------- Telegram, local mode, aliases
def test_ingestion_summary_is_one_message_per_interval(app, c):
    from backend.app.monitor import send_ingest_summary
    ctx = app.state.ctx
    ctx.take_ingest_count()
    for i in range(3):
        add(c, f"s{i}")
    before = len(ctx.alerter.sent)
    assert "3 log(s) ingested" in send_ingest_summary(ctx)
    assert send_ingest_summary(ctx) is None and len(ctx.alerter.sent) == before + 1


def test_local_mode_admin_has_a_per_user_chain_too(tmp_path):
    from backend.api.auth import LOCAL_ADMIN_USER_ID
    app = create_app(make_settings(tmp_path), run_monitor=False)
    with TestClient(app) as c:
        tok = c.post("/api/auth/login", json={"username": "admin", "password": "test-api-key"}).json()["access_token"]
        r = c.post("/logs", json={"message": "local"}, headers=bearer(tok))
        assert r.status_code == 201 and r.json()["user_id"] == LOCAL_ADMIN_USER_ID


def test_quai_env_aliases_are_accepted(monkeypatch, tmp_path):
    from backend.app import config as cfg
    for k in ("RPC_URL", "CYPRUS1_PK", "QUAI_RPC_URL", "QUAI_PRIVATE_KEY", "CONTRACT_ADDRESS", "MODE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("QUAI_RPC_URL", "https://orchard.rpc.quai.network/cyprus1")
    monkeypatch.setenv("QUAI_PRIVATE_KEY", "0x" + "1" * 64)
    s = cfg.load_settings(tmp_path / "none.env")
    assert s.rpc_url == "https://orchard.rpc.quai.network/cyprus1" and s.cyprus1_pk
    monkeypatch.setenv("RPC_URL", "https://primary.example")
    assert cfg.load_settings(tmp_path / "none.env").rpc_url == "https://primary.example"  # canonical name wins


# --------------------------------------------------------------------- quai_service retries
def test_quai_service_retries_connection_errors_then_reports_clearly(monkeypatch):
    import backend.blockchain.quai_service as qs
    monkeypatch.setattr(qs.time, "sleep", lambda s: None)
    calls = []

    def refuse(request):
        calls.append(1)
        raise httpx.ConnectError("refused", request=request)
    a = QuaiServiceAnchorer("0x" + "2" * 40, transport=httpx.MockTransport(refuse))
    with pytest.raises(AnchorError, match="after 3 attempts"):
        a.anchor("ab" * 32, 1)
    assert len(calls) == 3
    ok_after = iter([None])

    def once_then_ok(request):
        if next(ok_after, "ok") is None:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json={"tx_hash": "0x" + "1" * 64, "block_number": 5, "block_timestamp": "t"})
    assert QuaiServiceAnchorer("0x" + "2" * 40, transport=httpx.MockTransport(once_then_ok)).anchor("ab" * 32, 1)["block_number"] == 5

    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)
    with pytest.raises(AnchorPending):
        QuaiServiceAnchorer("0x" + "2" * 40, transport=httpx.MockTransport(timeout)).anchor("ab" * 32, 1)
    assert QuaiServiceAnchorer("0x" + "2" * 40, transport=httpx.MockTransport(timeout)).status() is None  # GET: no crash
    assert isinstance(AlreadyAnchored("x"), AnchorError)


# --------------------------------------------------------------------- Postgres RLS (own rows only)
PG_URL = os.getenv("PG_TEST_URL")


@pytest.mark.skipif(not PG_URL, reason="PG_TEST_URL not set")
def test_rls_users_read_only_their_own_rows_on_postgres():
    from sqlalchemy.exc import ProgrammingError
    from backend.database.db import apply_schema, make_engine
    eng = make_engine(PG_URL)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        conn.exec_driver_sql(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;"
            " IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF; END $$;")
        conn.exec_driver_sql("GRANT USAGE ON SCHEMA public TO anon, authenticated;"
                             " ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;")
        # Supabase-compatible auth.uid(): the user id from the request's JWT claims
        conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS auth; CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS"
                             " $f$ SELECT nullif(current_setting('request.jwt.claims', true)::json->>'sub', '')::uuid $f$;"
                             " GRANT USAGE ON SCHEMA auth TO anon, authenticated; GRANT EXECUTE ON FUNCTION auth.uid() TO anon, authenticated;")
    raw = eng.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute((ROOT / "supabase/migrations/20261121000000_silent_schema.sql").read_text())
        raw.commit()
    finally:
        raw.close()
    app = create_app(make_settings(Path("/tmp"), database_url=PG_URL, supabase_url=SUPA_URL,
                                   supabase_jwt_secret=SUPA_SECRET), run_monitor=False)
    app = with_fake_chain(app, Path(os.environ.get("TMPDIR", "/tmp")) / f"rls-{uuid.uuid4().hex}")
    with TestClient(app) as c:
        add(c, "A1")
        add(c, "A2")
        add(c, "B1", B)
        c.post("/merkle/build", headers=A)
        assert c.post("/anchor", headers=A).status_code == 200
    for uid, n_logs, n_roots, n_anchors in [(USER_ID, 2, 1, 1), (OTHER_ID, 1, 0, 0)]:
        with eng.begin() as conn:
            conn.execute(text("SET LOCAL ROLE authenticated"))
            conn.execute(text("SELECT set_config('request.jwt.claims', :c, true)"), {"c": f'{{"sub":"{uid}"}}'})
            assert conn.execute(text("SELECT count(*) FROM logs")).scalar() == n_logs
            assert conn.execute(text("SELECT count(*) FROM merkle_roots")).scalar() == n_roots
            assert conn.execute(text("SELECT count(*) FROM anchors")).scalar() == n_anchors
    for role, stmt in [("authenticated", "UPDATE logs SET message='x'"), ("authenticated", "DELETE FROM logs"),
                       ("anon", "SELECT * FROM logs")]:
        with pytest.raises(ProgrammingError, match="permission denied"):
            with eng.begin() as conn:
                conn.execute(text(f"SET LOCAL ROLE {role}"))
                conn.execute(text(stmt))
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public; DROP SCHEMA auth CASCADE;"))
