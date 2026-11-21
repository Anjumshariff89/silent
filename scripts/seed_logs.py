"""Seed real test logs through the ingest API (the same path the Windows agent uses).

Every log goes through POST /api/logs/ingest with the API key from .env, so it is validated, gets the next
sequential seq_id and is SHA-256 chained like any other log. Seed logs are labelled "(seed)" in their message
and use agent_id "seed-script" so they are never mistaken for Windows Security events.

Windows PowerShell:
    .\\.venv\\Scripts\\python.exe scripts\\seed_logs.py --count 20
    .\\.venv\\Scripts\\python.exe scripts\\seed_logs.py --count 20 --verify --build-merkle
"""
from __future__ import annotations

import argparse
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from backend.app.config import load_settings  # noqa: E402

EVENTS = [  # (event_id, event_type, severity, message)
    (4624, "logon", "info", "An account was successfully logged on"),
    (4634, "logoff", "info", "An account was logged off"),
    (4672, "special_privileges", "warning", "Special privileges assigned to new logon"),
    (4673, "privileged_service", "warning", "A privileged service was called"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Insert test logs through the ingest API")
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("--agent-id", default="seed-script")
    ap.add_argument("--verify", action="store_true", help="run POST /api/verify afterwards")
    ap.add_argument("--build-merkle", action="store_true", help="build a Merkle batch from unbatched logs afterwards")
    args = ap.parse_args()

    settings = load_settings()  # reads API_KEY from .env (never printed)
    host = socket.gethostname()
    base = args.server.rstrip("/")
    with httpx.Client(timeout=15) as client:
        try:
            client.get(f"{base}/health").raise_for_status()
        except httpx.HTTPError as exc:
            print(f"Backend not reachable at {base} ({type(exc).__name__}). Start it first: .\\run-dev.ps1")
            return 2
        seq_ids = []
        for i in range(args.count):
            event_id, event_type, severity, message = EVENTS[i % len(EVENTS)]
            body = {"agent_id": args.agent_id, "event_id": event_id, "event_type": event_type, "severity": severity,
                    "source_host": host, "username": f"seed.user{i % 5 + 1}", "source_ip": "127.0.0.1",
                    "message": f"{message} (seed)",
                    "event_time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
            r = client.post(f"{base}/api/logs/ingest", json=body, headers={"X-API-Key": settings.api_key})
            if r.status_code != 200:
                print(f"ingest failed: HTTP {r.status_code} {r.text[:200]}")
                return 1
            seq_ids.append(r.json()["seq_id"])
        print(f"ingested {len(seq_ids)} logs: seq_id {seq_ids[0]}..{seq_ids[-1]}" if seq_ids else "nothing ingested")

        if args.verify or args.build_merkle:
            tok = client.post(f"{base}/api/auth/login", json={"username": "admin", "password": settings.api_key})
            tok.raise_for_status()
            h = {"Authorization": f"Bearer {tok.json()['access_token']}"}
            if args.verify:
                v = client.post(f"{base}/api/verify", headers=h).json()
                print(f"chain verification: {v['result']} ({v['checked_count']} logs, {len(v['issues'])} issue(s))")
            if args.build_merkle:
                b = client.post(f"{base}/api/merkle/build", headers=h)
                if b.status_code == 200:
                    j = b.json()
                    print(f"merkle batch {j['batch_id']}: seq {j['from_seq']}-{j['to_seq']}, root {j['root']}")
                else:
                    print(f"merkle build: HTTP {b.status_code} {b.json().get('detail')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
