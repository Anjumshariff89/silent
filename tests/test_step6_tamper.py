"""Step 6: tamper detection on sandbox copies of synthetic data."""
import pytest

from backend.crypto.tamper_simulator import fingerprint, make_sandbox, tamper
from backend.crypto.verifier import verify_chain
from backend.database import repo


def _verify(engine):
    with engine.connect() as conn:
        return verify_chain(repo.fetch_chain_rows(conn))


@pytest.fixture
def live(app, ingest):
    ingest(10)
    return app.state.ctx.engine


def test_clean_chain_passes(live, client, jwt_headers):
    r = client.post("/api/verify", headers=jwt_headers).json()
    assert r["result"] == "PASS" and r["checked_count"] == 10 and r["issues"] == []
    assert client.get("/api/integrity/status", headers=jwt_headers).json()["status"] == "green"


def test_modified_log_detected_with_exact_seq(live):
    before = fingerprint(live)
    sb = make_sandbox(live)
    tamper(sb, "modify", 4)
    r = _verify(sb)
    assert r["result"] == "FAIL"
    assert [(i["type"], i["seq_id"]) for i in r["issues"]] == [("modified", 4)]
    assert fingerprint(live) == before


def test_deleted_log_detected_as_gap(live):
    before = fingerprint(live)
    sb = make_sandbox(live)
    tamper(sb, "delete", 6)
    r = _verify(sb)
    assert [(i["type"], i["seq_id"]) for i in r["issues"]] == [("missing", 6)]
    assert "6" in r["issues"][0]["detail"] and r["issues"][0]["missing_seq_ids"] == [6]
    assert fingerprint(live) == before


def test_reordered_logs_detected(live):
    before = fingerprint(live)
    sb = make_sandbox(live)
    tamper(sb, "reorder", 3)  # swap 3 and 4
    r = _verify(sb)
    types = {i["type"] for i in r["issues"]}
    assert types == {"reordered"}
    assert {3, 4} <= {i["seq_id"] for i in r["issues"]}
    assert fingerprint(live) == before


def test_delete_and_renumber_is_detected(live):
    """Attacker deletes seq 5 and shifts later rows down to hide the gap."""
    sb = make_sandbox(live)
    from sqlalchemy import text
    with sb.begin() as c:
        c.execute(text("PRAGMA defer_foreign_keys = ON"))
        c.execute(text("DELETE FROM hash_chain WHERE seq_id=5"))
        c.execute(text("DELETE FROM security_logs WHERE seq_id=5"))
        for s in range(6, 11):
            for t in ("hash_chain", "security_logs"):
                c.execute(text(f"UPDATE {t} SET seq_id=:n WHERE seq_id=:o"), {"n": s - 1, "o": s})
    r = _verify(sb)
    assert r["result"] == "FAIL" and r["issues"][0]["type"] == "missing" and r["issues"][0]["seq_id"] == 5


def test_api_verify_on_tampered_live_db_creates_incident_and_alert(app, live, client, jwt_headers):
    """Simulates an attacker editing the DB directly (temp test DB = synthetic data)."""
    from sqlalchemy import text
    with live.begin() as c:
        c.execute(text("UPDATE security_logs SET source_ip='6.6.6.6' WHERE seq_id=7"))
    r = client.post("/api/verify", headers=jwt_headers).json()
    assert r["result"] == "FAIL" and r["issues"][0]["seq_id"] == 7 and len(r["incidents_created"]) == 1
    inc = client.get("/api/incidents", headers=jwt_headers).json()["items"][0]
    assert inc["type"] == "modified" and inc["seq_id"] == 7 and inc["alert_channel"] == "console" and inc["alert_sent"]
    assert any("MODIFIED at seq 7" in a for a in app.state.ctx.alerter.sent)
    assert client.get("/api/integrity/status", headers=jwt_headers).json()["status"] == "red"


def test_tamper_demo_endpoints_are_removed(live, client, jwt_headers):
    """Real mode: the sandbox demo is gone; tamper detection runs only on real data via POST /api/verify."""
    assert client.post("/api/demo/tamper", json={"seq_id": 2}, headers=jwt_headers).status_code == 404
    assert client.post("/api/demo/reset", headers=jwt_headers).status_code == 404


def test_integrity_status_turns_red_on_real_tamper_and_green_after_resolve(app, live, client, jwt_headers):
    from sqlalchemy import text
    assert client.post("/api/verify", headers=jwt_headers).json()["result"] == "PASS"
    assert client.get("/api/integrity/status", headers=jwt_headers).json()["status"] == "green"
    with live.begin() as c:  # attacker edits the (temporary test) database directly
        c.execute(text("UPDATE security_logs SET message='edited' WHERE seq_id=2"))
    assert client.post("/api/verify", headers=jwt_headers).json()["result"] == "FAIL"
    assert client.get("/api/integrity/status", headers=jwt_headers).json()["status"] == "red"


def test_telegram_alert_real_path_uses_api_and_never_leaks_token(capsys):
    import httpx
    from backend.integrations.alerts import Alerter
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"ok": True})

    a = Alerter("123:SECRET", "42", transport=httpx.MockTransport(handler))
    assert a.send("x") == ("telegram", True) and seen["url"].endswith("/sendMessage")

    def fail(req):
        raise httpx.ConnectError("boom https://api.telegram.org/bot123:SECRET/sendMessage")
    b = Alerter("123:SECRET", "42", transport=httpx.MockTransport(fail))
    assert b.send("y")[0] == "console(telegram-failed)"
    assert "SECRET" not in capsys.readouterr().out
