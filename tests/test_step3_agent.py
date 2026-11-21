"""Step 3: real Windows collector only (no synthetic fallback), HTTPS enforcement, append-only agent."""
import ast
import builtins
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from backend.agent import collector as col
from backend.agent.agent import LogAgent, require_https

AGENT_DIR = Path(__file__).resolve().parents[1] / "backend" / "agent"
REQUIRED = {"event_id", "event_type", "severity", "source_host", "username", "source_ip", "message", "event_time"}


class _OneEventCollector:
    """Test double standing in for the Windows collector (the agent code under test is unchanged)."""
    mode = "windows"
    hostname = "WIN-TEST-01"

    def collect(self, max_events=10):
        return [{"event_id": 4624, "event_type": "logon", "severity": "info", "source_host": self.hostname,
                 "username": "test.user", "source_ip": "10.0.0.5", "message": "test event",
                 "event_time": "2026-11-21T10:00:00Z"}]


def test_no_synthetic_fallback_when_pywin32_missing(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("win32"):
            raise ImportError("No module named 'win32evtlog'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert col.windows_collector_available() is False
    with pytest.raises(col.CollectorUnavailable, match="Windows"):
        col.make_collector("windows")
    assert not hasattr(col, "SimulatorCollector")  # the synthetic generator is gone


def test_agent_exits_with_clear_message_when_no_windows_log(monkeypatch, capsys):
    import sys
    from backend.agent import agent as agent_mod
    monkeypatch.setattr(sys, "argv", ["agent"])
    monkeypatch.setattr(agent_mod, "make_collector",
                        lambda prefer="auto": (_ for _ in ()).throw(col.CollectorUnavailable("not Windows")))
    with pytest.raises(SystemExit) as e:
        agent_mod.main()
    assert e.value.code == 3
    out = capsys.readouterr().out
    assert "not started: not Windows" in out and "/api/logs/ingest" in out


def test_https_required_for_remote_hosts():
    require_https("https://logs.example.com")
    require_https("http://127.0.0.1:8000")
    with pytest.raises(ValueError, match="https"):
        require_https("http://logs.example.com")


class _Recorder(BaseHTTPRequestHandler):
    seen: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Recorder.seen.append((self.command, self.path, self.headers.get("X-API-Key"), body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "accepted", "seq_id": len(_Recorder.seen)}).encode())

    def log_message(self, *a):
        pass


def test_agent_sends_events_and_heartbeats_with_api_key():
    srv = HTTPServer(("127.0.0.1", 0), _Recorder)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        agent = LogAgent(f"http://127.0.0.1:{srv.server_port}", "k-test", "agent-t", _OneEventCollector())
        agent.send_event(_OneEventCollector().collect(1)[0])
        agent.send_heartbeat()
    finally:
        srv.shutdown()
    paths = [(m, p, k) for m, p, k, _ in _Recorder.seen]
    assert ("POST", "/api/logs/ingest", "k-test") in paths
    assert ("POST", "/api/heartbeats", "k-test") in paths


def test_agent_has_no_edit_or_delete_code_path():
    """Static check: agent code issues only POSTs and contains no update/delete calls."""
    forbidden_attrs = {"put", "patch", "delete"}
    for f in AGENT_DIR.glob("*.py"):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in forbidden_attrs:
                pytest.fail(f"{f.name}: uses .{node.attr}()")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                v = node.value.upper()
                assert "DELETE FROM" not in v and "UPDATE " not in v and "CLEAREVENTLOG" not in v, f.name
            if isinstance(node, ast.Attribute) and node.attr in {"ClearEventLog", "BackupEventLog", "ReportEvent"}:
                pytest.fail(f"{f.name}: touches system log via {node.attr}")
