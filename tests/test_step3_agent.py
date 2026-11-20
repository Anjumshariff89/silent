"""Step 3: collector simulator, fallback, HTTPS enforcement, append-only agent."""
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


def test_simulator_events_have_contract_fields_and_monitored_ids():
    events = col.SimulatorCollector(seed=1).collect(10)
    assert events
    for e in events:
        assert set(e) == REQUIRED
        assert e["event_id"] in (4624, 4634, 4672, 4673)
        assert e["username"].startswith("synthetic.")
        assert e["source_ip"].startswith("10.0.0.")


def test_fallback_when_pywin32_missing(monkeypatch, capsys):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("win32"):
            raise ImportError("No module named 'win32evtlog'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert col.windows_collector_available() is False
    c = col.make_collector("windows")
    assert isinstance(c, col.SimulatorCollector) and c.mode == "simulator"
    assert "falling back to simulator" in capsys.readouterr().out


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
        agent = LogAgent(f"http://127.0.0.1:{srv.server_port}", "k-test", "agent-t", col.SimulatorCollector(seed=2))
        agent.send_event(col.SimulatorCollector(seed=3).collect(1)[0])
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
