"""Supabase Auth: token verification (HS256 + JWKS), protected routes, app routes, CORS, migration + RLS."""
import json
import os
import time
import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.factory import create_app
from tests.conftest import TEST_API_KEY, make_settings, sample_event, with_fake_chain

ROOT = Path(__file__).resolve().parents[1]
SUPA_URL = "https://abcdefghijklmnop.supabase.co"
SUPA_SECRET = "test-supabase-jwt-secret-" + "s" * 40
USER_ID = str(uuid.uuid4())


def supa_token(secret=SUPA_SECRET, alg="HS256", **over):
    now = int(time.time())
    claims = {"sub": USER_ID, "aud": "authenticated", "role": "authenticated", "email": "analyst@example.test",
              "iss": f"{SUPA_URL}/auth/v1", "iat": now, "exp": now + 3600}
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}
    headers = {"kid": "test-key"} if alg != "HS256" else None
    return jwt.encode(claims, secret, algorithm=alg, headers=headers)


def bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def supa_app(tmp_path):
    s = make_settings(tmp_path, supabase_url=SUPA_URL, supabase_jwt_secret=SUPA_SECRET,
                      frontend_origin="https://dashboard.example.test")
    return with_fake_chain(create_app(s, run_monitor=False), tmp_path)


@pytest.fixture
def sc(supa_app):
    with TestClient(supa_app) as c:
        yield c


def test_valid_supabase_token_opens_every_protected_route_and_yields_user_id(sc, supa_app):
    h = bearer(supa_token())
    for path in ["/logs", "/api/logs", "/verify", "/anchors", "/api/integrity/status", "/api/merkle/batches",
                 "/api/blockchain/status", "/api/agents", "/api/incidents"]:
        assert sc.get(path, headers=h).status_code == 200, path
    from backend.api.auth import verify_bearer
    assert verify_bearer(supa_app.state.ctx.settings, supa_token())["user_id"] == USER_ID


@pytest.mark.parametrize("why,tok", [
    ("expired", lambda: supa_token(exp=int(time.time()) - 10)),
    ("wrong secret", lambda: supa_token(secret="not-the-project-secret-" + "z" * 40)),
    ("anon key (role anon, no user aud)", lambda: supa_token(role="anon", aud=None, sub=None)),
    ("service_role key", lambda: supa_token(role="service_role", aud=None)),
    ("other project issuer", lambda: supa_token(iss="https://other.supabase.co/auth/v1")),
    ("alg none", lambda: jwt.encode({"sub": USER_ID, "aud": "authenticated", "role": "authenticated"}, None, algorithm="none")),
    ("garbage", lambda: "not.a.jwt"),
])
def test_invalid_tokens_get_401(sc, why, tok):
    for path in ["/logs", "/verify", "/anchors", "/api/logs"]:
        assert sc.get(path, headers=bearer(tok())).status_code == 401, (why, path)


def test_missing_token_is_401_but_health_is_public(sc):
    for path in ["/logs", "/verify", "/anchors"]:
        assert sc.get(path).status_code == 401
    assert sc.post("/merkle/build").status_code == 401 and sc.post("/anchor").status_code == 401
    h = sc.get("/health").json()
    assert h["status"] == "ok" and h["integrations"]["auth"] == "SUPABASE"
    assert SUPA_SECRET not in json.dumps(h)


def test_local_login_and_local_tokens_are_refused_when_supabase_is_on(sc, supa_app):
    assert sc.post("/api/auth/login", json={"username": "admin", "password": TEST_API_KEY}).status_code == 403
    from backend.api.auth import create_token
    local = create_token(supa_app.state.ctx.settings.jwt_secret)
    assert sc.get("/logs", headers=bearer(local)).status_code == 401


def test_es256_token_verified_with_project_jwks(sc, monkeypatch):
    """New Supabase projects sign with asymmetric keys: verified via SUPABASE_URL/auth/v1/.well-known/jwks.json."""
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": "test-key", "alg": "ES256", "use": "sig"})
    fetched = []

    def fake_fetch(self):
        fetched.append(self.uri)
        return {"keys": [jwk]}

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", fake_fetch)
    import backend.api.auth as auth
    auth._jwks_clients.clear()
    assert sc.get("/logs", headers=bearer(supa_token(secret=key, alg="ES256"))).status_code == 200
    assert fetched == [f"{SUPA_URL}/auth/v1/.well-known/jwks.json"]
    other = ec.generate_private_key(ec.SECP256R1())  # signed by a key not in the project's JWKS
    assert sc.get("/logs", headers=bearer(supa_token(secret=other, alg="ES256"))).status_code == 401


def test_shared_soc_chain_routes_work_with_supabase_tokens(sc, supa_app):
    """The shared agent chain (/api/...) keeps working with Supabase sign-in: ingest (API key), verify, tamper."""
    h = bearer(supa_token())
    for i in range(3):
        assert sc.post("/api/logs/ingest", json=sample_event(i), headers={"X-API-Key": TEST_API_KEY}).status_code == 200
    assert sc.get("/api/logs", headers=h).json()["total"] == 3
    assert sc.post("/api/verify", headers=h).json()["result"] == "PASS"
    with supa_app.state.ctx.engine.begin() as conn:
        conn.execute(text("UPDATE security_logs SET username='attacker' WHERE seq_id=2"))
    v = sc.post("/api/verify", headers=h).json()
    assert v["result"] == "FAIL" and any(i["seq_id"] == 2 for i in v["issues"])


def test_websocket_accepts_supabase_token_only(sc):
    with sc.websocket_connect(f"/ws/live?token={supa_token()}") as ws:
        assert json.loads(ws.receive_text())["type"] == "hello"
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with sc.websocket_connect("/ws/live?token=bad") as ws:
            ws.receive_text()


def test_cors_allows_configured_frontend_origin_only(sc):
    pre = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}
    ok = sc.options("/logs", headers={"Origin": "https://dashboard.example.test", **pre})
    assert ok.headers.get("access-control-allow-origin") == "https://dashboard.example.test"
    assert sc.options("/logs", headers={"Origin": "http://127.0.0.1:3000", **pre}).headers.get("access-control-allow-origin")
    assert "access-control-allow-origin" not in sc.options("/logs", headers={"Origin": "https://evil.example", **pre}).headers


def test_supabase_migration_is_schema_plus_rls_in_sync():
    mig = (ROOT / "supabase/migrations/20261121000000_silent_schema.sql").read_text()
    for part in ["backend/database/schema_postgres.sql", "backend/database/rls_supabase.sql"]:
        assert (ROOT / part).read_text() in mig, f"{part} changed: regenerate the migration"


PG_URL = os.getenv("PG_TEST_URL")


@pytest.mark.skipif(not PG_URL, reason="PG_TEST_URL not set")
def test_rls_signed_in_users_read_only_anon_nothing_on_postgres():
    from sqlalchemy.exc import ProgrammingError
    from backend.database.db import make_engine
    eng = make_engine(PG_URL)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        c.exec_driver_sql("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;"
                          " IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF; END $$;")
        c.exec_driver_sql("GRANT USAGE ON SCHEMA public TO anon, authenticated;"
                          " ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;")
    mig = (ROOT / "supabase/migrations/20261121000000_silent_schema.sql").read_text()
    for _ in range(2):  # idempotent; raw cursor so psycopg2 does not treat format()'s %I as a parameter
        raw = eng.raw_connection()
        try:
            with raw.cursor() as cur:
                cur.execute(mig)
            raw.commit()
        finally:
            raw.close()
    with eng.begin() as c:
        c.execute(text("INSERT INTO agents(agent_id, hostname, agent_version, collector_mode, registered_at)"
                       " VALUES ('a1','h','1','windows','2026-11-21T00:00:00Z')"))
        assert c.execute(text("SELECT count(*) FROM pg_tables WHERE schemaname='public' AND rowsecurity")).scalar() == 11
    with eng.begin() as c:
        c.execute(text("SET LOCAL ROLE authenticated"))
        assert c.execute(text("SELECT count(*) FROM agents")).scalar() == 1
    for role, stmt in [("authenticated", "UPDATE agents SET hostname='x'"), ("authenticated", "DELETE FROM agents"),
                       ("authenticated", "INSERT INTO agents(agent_id, hostname, agent_version, collector_mode, registered_at) VALUES ('e','h','1','windows','t')"),
                       ("anon", "SELECT * FROM agents"), ("anon", "SELECT * FROM security_logs")]:
        with pytest.raises(ProgrammingError, match="permission denied"):
            with eng.begin() as c:
                c.execute(text(f"SET LOCAL ROLE {role}"))
                c.execute(text(stmt))
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))


def test_repeated_verification_does_not_duplicate_open_incidents_or_alerts(sc, supa_app):
    h = bearer(supa_token())
    for i in range(3):
        sc.post("/api/logs/ingest", json=sample_event(i), headers={"X-API-Key": TEST_API_KEY})
    with supa_app.state.ctx.engine.begin() as conn:
        conn.execute(text("UPDATE security_logs SET username='attacker' WHERE seq_id=2"))
    first, second = sc.post("/api/verify", headers=h).json(), sc.post("/api/verify", headers=h).json()
    assert first["result"] == second["result"] == "FAIL"
    assert len(first["incidents_created"]) == 1 and second["incidents_created"] == []
    assert second["incidents_already_open"] == first["incidents_created"]
    assert sc.get("/api/incidents", headers=h).json()["total"] == 1
    assert sc.post("/api/incidents/resolve", headers=h).status_code == 200
    third = sc.post("/api/verify", headers=h).json()                     # still tampered, old incident resolved -> new one
    assert len(third["incidents_created"]) == 1


def test_unexpected_errors_are_json_500_with_cors_headers(supa_app):
    """A crash must not look like 'Cannot reach the API' in the browser: JSON 500 + CORS headers."""
    from fastapi import APIRouter
    r = APIRouter()

    @r.get("/boom")
    def boom():
        raise ValueError("corrupt row")
    supa_app.include_router(r)
    with TestClient(supa_app, raise_server_exceptions=False) as c:
        res = c.get("/boom", headers={"Origin": "http://127.0.0.1:3000"})
    assert res.status_code == 500 and res.json()["detail"].startswith("Internal server error (ValueError)")
    assert res.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"
    assert "corrupt row" not in res.text
