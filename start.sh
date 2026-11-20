#!/usr/bin/env bash
# Linux/macOS equivalent of start.ps1 (same steps, same ports, same files).
#   ./start.sh            start backend + agent + dashboard
#   ./start.sh --verifier also start the standalone verifier
#   ./start.sh --stop     stop everything started by this script
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"; DATA="$ROOT/data"; LOGS="$DATA/runtime_logs"; PIDS="$DATA/pids"
API_PORT="${API_PORT:-8000}"; WEB_PORT="${WEB_PORT:-3000}"
PY="$ROOT/.venv/bin/python"
mkdir -p "$LOGS"

kill_tree() {  # kill a process and all its descendants (npm -> sh -> next-server)
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$child"; done
  kill "$1" 2>/dev/null || true
}
stop_all() {
  if [ -f "$PIDS" ]; then
    while read -r name pid; do
      if kill -0 "$pid" 2>/dev/null; then
        kill_tree "$pid"
        echo "stopped $name (pid $pid)"
      fi
    done < "$PIDS"
    rm -f "$PIDS"
  else
    echo "nothing to stop"
  fi
}
wait_http() { for _ in $(seq 1 "$2"); do curl -fsS -o /dev/null "$1" 2>/dev/null && return 0; sleep 1; done; return 1; }

[ "${1:-}" = "--stop" ] && { stop_all; exit 0; }
[ -f "$PIDS" ] && { echo "==> previous run found, stopping it"; stop_all; }

echo "==> Checking prerequisites"
for port in "$API_PORT" "$WEB_PORT"; do   # allow up to 10 s for a just-stopped run to release ports
  for i in $(seq 1 10); do curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$port/" || continue 2; sleep 1; done
  echo "Port $port is already in use by another process. Stop it first (./start.sh --stop)."; exit 1
done
command -v python3.12 >/dev/null || { echo "Python 3.12 not found"; exit 1; }
command -v node >/dev/null || { echo "Node.js not found"; exit 1; }

STAMP="$DATA/.requirements.sha256"; REQ_HASH="$(sha256sum requirements.txt | cut -d' ' -f1)"
if [ ! -x "$PY" ]; then echo "==> Creating .venv (Python 3.12)"; python3.12 -m venv .venv; fi
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$REQ_HASH" ]; then
  echo "==> Installing pinned Python dependencies"
  "$PY" -m pip install -q -r requirements.txt
  echo "$REQ_HASH" > "$STAMP"
fi
[ -f .env ] || { cp .env.example .env; echo "Created .env from .env.example (SIMULATED). Edit it yourself to add keys."; }

( cd frontend
  [ -d node_modules ] || { echo "==> npm ci"; npm ci --no-audit --no-fund; }
  [ -f .next/BUILD_ID ] || { echo "==> Building dashboard"; NEXT_TELEMETRY_DISABLED=1 npm run build; } )

: > "$PIDS"
echo "==> Starting backend on http://127.0.0.1:$API_PORT"
nohup "$PY" -m uvicorn backend.main:app --host 127.0.0.1 --port "$API_PORT" < /dev/null > "$LOGS/backend.log" 2>&1 &
echo "backend $!" >> "$PIDS"
wait_http "http://127.0.0.1:$API_PORT/api/health" 60 || { echo "backend not healthy; see $LOGS/backend.log"; exit 1; }

echo "==> Starting log agent"
nohup "$PY" -m backend.agent.agent --server "http://127.0.0.1:$API_PORT" --collector auto < /dev/null > "$LOGS/agent.log" 2>&1 &
echo "agent $!" >> "$PIDS"

if [ "${1:-}" = "--verifier" ]; then
  nohup "$PY" -m backend.verifier_service --interval 60 < /dev/null > "$LOGS/verifier.log" 2>&1 &
  echo "verifier $!" >> "$PIDS"
fi

echo "==> Starting dashboard on http://127.0.0.1:$WEB_PORT"
# backgrounded subshell + exec: $! is the real npx PID and no process keeps this script's stdout open
( cd frontend && NEXT_TELEMETRY_DISABLED=1 exec nohup npx next start -p "$WEB_PORT" < /dev/null > "$LOGS/frontend.log" 2>&1 ) &
echo "frontend $!" >> "$PIDS"
wait_http "http://127.0.0.1:$WEB_PORT/login" 60 || { echo "dashboard did not start; see $LOGS/frontend.log"; exit 1; }

echo
echo "All services running:"
"$PY" - "$API_PORT" "$WEB_PORT" <<'EOF'
import json, sys, urllib.request
api, web = sys.argv[1], sys.argv[2]
h = json.load(urllib.request.urlopen(f"http://127.0.0.1:{api}/api/health"))
print(f"  Backend   http://127.0.0.1:{api}/docs  status={h['status']} db={h['database']['backend']}")
print(f"  Dashboard http://127.0.0.1:{web}")
print("  Integrations: " + " ".join(f"{k}={v}" for k, v in h["integrations"].items()))
print("  Login: admin / " + ("dev-local-api-key (simulator dev key)" if h["dev_api_key_in_use"] else "<your API_KEY>"))
EOF
echo "Stop with: ./start.sh --stop"
