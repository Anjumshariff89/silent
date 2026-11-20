# API reference

- **Machine-readable spec:** [`openapi.json`](openapi.json) (OpenAPI 3.1, exported from the running FastAPI app).
- **Interactive docs:** start the backend and open `http://127.0.0.1:8000/docs` (Swagger UI) or `/redoc`.
- **Full request/response JSON contract with examples:** [`../PROJECT_STATE.md`](../PROJECT_STATE.md#api-contract).

## Authentication

| Caller | Header |
|---|---|
| Log agent | `X-API-Key: <API_KEY>` (ingest + heartbeats) |
| Dashboard / analyst | `Authorization: Bearer <JWT>` from `POST /api/auth/login` `{ "username": "admin", "password": "<API_KEY>" }` |
| WebSocket | `ws://127.0.0.1:8000/ws/live?token=<JWT>` (bad token → close code 1008) |

## Endpoints (23 HTTP operations + 1 WebSocket)

| Method | Path | Purpose | Tag |
|---|---|---|---|
| `GET` | `/api/agents` | Get Agents | agents |
| `POST` | `/api/auth/login` | Login | auth |
| `POST` | `/api/blockchain/anchor` | Post Anchor | blockchain |
| `GET` | `/api/blockchain/status` | Get Status | blockchain |
| `GET` | `/api/chain` | Get Chain | integrity |
| `POST` | `/api/demo/reset` | Demo Reset | demo |
| `POST` | `/api/demo/tamper` | Demo Tamper | demo |
| `GET` | `/api/evidence/{batch_id}/json` | Evidence Json | evidence |
| `GET` | `/api/evidence/{batch_id}/pdf` | Evidence Pdf | evidence |
| `GET` | `/api/health` | Health | health |
| `POST` | `/api/heartbeats` | Post Heartbeat | agents |
| `GET` | `/api/heartbeats` | Get Heartbeats | agents |
| `GET` | `/api/incidents` | Get Incidents | integrity |
| `POST` | `/api/incidents/resolve` | Resolve Incidents | integrity |
| `GET` | `/api/integrity/status` | Get Integrity Status | integrity |
| `GET` | `/api/logs` | Get Logs | logs |
| `POST` | `/api/logs/ingest` | Ingest | logs |
| `GET` | `/api/merkle/batches` | List Batches | merkle |
| `POST` | `/api/merkle/build` | Post Build | merkle |
| `GET` | `/api/merkle/{batch_id}` | Get Merkle | merkle |
| `GET` | `/api/merkle/{batch_id}/proof/{seq_id}` | Get Proof | merkle |
| `POST` | `/api/proof/verify` | Post Proof Verify | blockchain |
| `POST` | `/api/verify` | Verify | integrity || `WS` | `/ws/live` | Live push: `log`, `heartbeat`, `agent_status`, `incident`, `integrity`, `anchor` | live |

There are **no** PUT/PATCH/DELETE routes (enforced by `test_no_update_or_delete_routes_exist`): logs are append-only.

## Quick curl tour (PowerShell: use `curl.exe`)

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"agent_id":"agent-win-01","event_id":4624,"event_type":"logon","source_host":"WIN-SYNTH-01","message":"synthetic","event_time":"2026-11-20T10:00:00Z"}' \
  http://127.0.0.1:8000/api/logs/ingest
TOKEN=$(curl -s -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"$API_KEY\"}" http://127.0.0.1:8000/api/auth/login | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/verify
```

## Error codes

`401` bad/missing key or JWT · `404` unknown batch/seq · `409` already anchored / overlapping batch ·
`422` validation error · `400` empty batch / bad tamper target · `503` RPC unreachable (REAL mode).
