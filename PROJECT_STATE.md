# PROJECT_STATE — Logs the Attacker Can't Erase (Quai Orchard edition)

Tamper-evident security logging: SHA-256 hash chains, Merkle trees, and blockchain anchoring on
**Quai Orchard Cyprus-1 testnet** (chain ID 15000).

> **What blockchain anchoring proves and does not prove:** an anchored Merkle root proves only
> that the *commitment* (the set of log hashes in that batch) has not changed since the moment it
> was anchored. It does **not** prove that a logged event actually happened, that the log source
> was honest, or that logs were not tampered with *before* anchoring.

## Current status

| Field | Value |
|---|---|
| Current step | Quai rebuild — Step 9 (Evidence reports) complete; Step 8 REAL mode still waits for keys + "approve" |
| Next step | Step 10 — Frontend (Quai labels, Orchard QuaiScan links, "Quai Orchard (REAL)" badge) |
| Python | 3.12 (venv at `.venv`) · Node.js LTS (quai-service, Hardhat, frontend) |
| Default mode | `MODE=simulator` (every integration falls back to a simulator when its key is empty) |
| Build host | Linux cloud container (target platform: Windows 11 / PowerShell) |
| History | `main` before this rebuild = Polygon Amoy edition (all 12 steps PASS). This edition replaces Polygon/web3.py with Quai via a Node.js `quais` service. |

## Phase checklist (Quai rebuild — every step is re-verified with a fresh report)

- [x] **Step 1** Setup and contract: Quai `.env.example` (10 keys), `backend/blockchain/quai-service/`, 4 branches, this contract
- [x] **Step 2** Database (schema.sql SQLite + Postgres/Supabase, 8 tables, restricted role)
- [~] **Step 3** Log agent: simulator, fallback, 10 s heartbeat, HTTPS + API key, append-only re-verified. **Real Windows Event Log collector NOT run (no Windows host).**
- [x] **Step 4** FastAPI core (ingest, logs, heartbeats, agents, health, API-key + JWT auth, /ws/live)
- [x] **Step 5** Hash chain (SHA-256 prev_hash/curr_hash)
- [x] **Step 6** Tamper detection (modified/missing/reordered, incidents, Telegram/console alert)
- [x] **Step 7** Merkle tree (root, inclusion proofs, merkle_batches)
- [~] **Step 8** Blockchain on Quai Orchard — simulator PASS; REAL deploy/anchor not yet run — (Solidity 0.8.20 `anchorRoot`, Hardhat `cyprus1`, Node.js quais service `/anchor` `/status`, simulator; **no broadcast until operator replies "approve"**)
- [x] **Step 9** Evidence reports (JSON bundle + PDF certificate with disclaimer, Orchard QuaiScan links)
- [ ] **Step 10** Frontend (SOC dashboard, "Quai Orchard (REAL)" / "SIMULATED" badges)
- [ ] **Step 11** End-to-end tests (6 scenarios)
- [ ] **Step 12** Docs and launch (start.ps1 launches backend, agent, quai-service, frontend; deployment evidence table)

## Git branches

| Branch | Used for |
|---|---|
| `main` | Merged, verified work only (Overall = PASS) |
| `feature/log-collection` | Steps 1–4 (setup, database, agent, API core) |
| `feature/tamper-detection` | Steps 5–7 (hash chain, tamper detection, Merkle) |
| `feature/blockchain` | Steps 8–9 (Quai contract, quai-service, evidence) |
| `feature/frontend` | Steps 10–12 (dashboard, E2E, docs) |
| `feature/quai-orchard` | Earlier Quai experiment, not by this build. Left untouched; not merged. |

## Environment variables (`.env`, git-ignored; `.env.example` holds exactly these 10)

| Variable | Default | Used by | Purpose |
|---|---|---|---|
| `MODE` | `simulator` | backend | `real` refuses to start without `API_KEY` and `JWT_SECRET` |
| `API_KEY` | empty (dev key in simulator) | backend, agent | Agent `X-API-Key`; dashboard password |
| `JWT_SECRET` | empty (random per start) | backend | Signs dashboard JWTs |
| `DATABASE_URL` | `sqlite:///./local.db` | backend | SQLite or Supabase Postgres |
| `RPC_URL` | empty | quai-service | Quai Orchard Cyprus-1 RPC (confirm on docs.qu.ai) |
| `CYPRUS1_PK` | empty | quai-service only | Throwaway Cyprus-1 testnet key. **Never** read by Python, never logged |
| `CHAIN_ID` | `15000` | backend, quai-service | Guard: refuse to sign if the RPC reports another chain |
| `CONTRACT_ADDRESS` | empty | backend, quai-service | Deployed `LogAnchor` on Cyprus-1 |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | empty | backend | Incident alerts |

## Integrations & fallbacks

| Integration | Env keys | REAL when | Fallback (SIMULATED) |
|---|---|---|---|
| Quai Orchard Cyprus-1 (Node.js `quais` service, chain 15000) | `RPC_URL`, `CYPRUS1_PK`, `CHAIN_ID`, `CONTRACT_ADDRESS` | all set **and** quai-service reachable (Step 8) | Local blockchain simulator |
| Supabase Postgres (SQLAlchemy) | `DATABASE_URL` | starts with `postgresql://` | SQLite |
| Telegram Bot API | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | both set | Console log |
| Windows Event Log (pywin32) | — | Windows + pywin32 importable | Event simulator |
| Orchard QuaiScan links | — (no key) | REAL anchors | none shown |

Not integrated (by requirement): Polygon, x402 Work, Hashference, AbuseIPDB, IPFS, OpenTimestamps, Slack.
Python never uses web3.py for Quai (Quai addresses are zone-specific and need the `quais` SDK).

---

## API contract

Base URL: `http://127.0.0.1:8000`. All bodies are JSON (`Content-Type: application/json`) unless noted.

### Authentication

| Caller | Mechanism | Header |
|---|---|---|
| Log agent | Static API key from `API_KEY` | `X-API-Key: <key>` |
| Dashboard | JWT (HS256, signed with `JWT_SECRET`, 60 min expiry) obtained from `POST /api/auth/login` | `Authorization: Bearer <jwt>` |
| Public | none | `GET /api/health` only |

### Standard error body

All errors use FastAPI's shape:

```json
{ "detail": "Invalid or missing API key" }
```

| Status | Meaning |
|---|---|
| 400 | Bad request (logical error, e.g. empty batch) |
| 401 | Missing/invalid API key or JWT |
| 404 | Resource not found (batch_id, seq_id) |
| 409 | Conflict (e.g. batch already anchored) |
| 422 | Validation error (malformed body) — FastAPI detail list |
| 503 | Dependency unavailable (RPC down in REAL mode) |

### Shared object: `SecurityLog`

```json
{
  "seq_id": 42,
  "agent_id": "agent-win-01",
  "event_id": 4624,
  "event_type": "logon",
  "severity": "info",
  "source_host": "WIN-SYNTH-01",
  "username": "synthetic.user1",
  "source_ip": "10.0.0.15",
  "message": "An account was successfully logged on (synthetic)",
  "event_time": "2026-11-20T14:30:00Z",
  "received_at": "2026-11-20T14:30:00.512Z",
  "prev_hash": "9f2c...64 hex chars",
  "curr_hash": "1ab7...64 hex chars",
  "merkle_batch_id": null
}
```

`event_type` ∈ `logon` (4624) | `logoff` (4634) | `special_privileges` (4672) | `privileged_service` (4673).
`severity` ∈ `info` | `warning` | `critical`.
Genesis log (`seq_id = 1`) uses `prev_hash = "0" * 64`.
`curr_hash = SHA-256(prev_hash || canonical_json(log fields without hashes))`, lowercase hex.

---

### `POST /api/auth/login` (dashboard)

Request:
```json
{ "username": "admin", "password": "..." }
```
Response 200:
```json
{ "access_token": "eyJhbGciOi...", "token_type": "bearer", "expires_in": 3600 }
```

### `POST /api/logs/ingest` — auth: API key

Request:
```json
{
  "agent_id": "agent-win-01",
  "event_id": 4624,
  "event_type": "logon",
  "severity": "info",
  "source_host": "WIN-SYNTH-01",
  "username": "synthetic.user1",
  "source_ip": "10.0.0.15",
  "message": "An account was successfully logged on (synthetic)",
  "event_time": "2026-11-20T14:30:00Z"
}
```
Response 200:
```json
{
  "status": "accepted",
  "seq_id": 42,
  "prev_hash": "9f2c...",
  "curr_hash": "1ab7...",
  "received_at": "2026-11-20T14:30:00.512Z"
}
```
Rules: `seq_id` is assigned by the server, strictly sequential (+1 per accepted log). Ingest is append-only; there is no update/delete endpoint. Errors: 401 (no/bad key), 422 (malformed).

### `GET /api/logs` — auth: JWT

Query params: `page` (default 1), `page_size` (default 50, max 500), `q` (free-text search over message/username/host), `event_id`, `event_type`, `severity`, `agent_id`, `source_ip`, `from` / `to` (ISO-8601 event_time range), `sort` (`asc` | `desc` by seq_id, default `desc`).

Response 200:
```json
{
  "items": [ { "...SecurityLog..." } ],
  "page": 1,
  "page_size": 50,
  "total": 1234
}
```

### `POST /api/heartbeats` — auth: API key

Request:
```json
{ "agent_id": "agent-win-01", "hostname": "WIN-SYNTH-01", "agent_version": "0.1.0", "collector_mode": "simulator", "sent_at": "2026-11-20T14:30:10Z" }
```
Response 200:
```json
{ "status": "ok", "agent_id": "agent-win-01", "received_at": "2026-11-20T14:30:10.101Z" }
```
`collector_mode` ∈ `windows` | `simulator`. Agents send every 10 s.

### `GET /api/heartbeats` — auth: JWT

Query: `agent_id` (optional), `limit` (default 100).
Response 200:
```json
{
  "items": [
    { "id": 991, "agent_id": "agent-win-01", "received_at": "2026-11-20T14:30:10.101Z", "collector_mode": "simulator" }
  ]
}
```

### `GET /api/agents` — auth: JWT

Response 200:
```json
{
  "items": [
    {
      "agent_id": "agent-win-01",
      "hostname": "WIN-SYNTH-01",
      "agent_version": "0.1.0",
      "collector_mode": "simulator",
      "last_heartbeat": "2026-11-20T14:30:10.101Z",
      "seconds_since_heartbeat": 4.2,
      "status": "online"
    }
  ]
}
```
Status rule: `online` if last heartbeat ≤ 20 s ago, `delayed` if ≤ 60 s, `offline` otherwise.

### `GET /api/health` — public

Response 200:
```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": { "status": "ok", "backend": "sqlite" },
  "integrations": {
    "blockchain": "SIMULATED",
    "database": "SIMULATED",
    "telegram": "SIMULATED",
    "windows_event_log": "SIMULATED"
  },
  "log_count": 1234,
  "time": "2026-11-20T14:30:12Z"
}
```
Each integration is `REAL` or `SIMULATED` and drives the dashboard badges. Key values are never returned.

### `POST /api/verify` — auth: JWT

Recomputes the full hash chain (or a range) and records the result.

Request (all optional):
```json
{ "from_seq": 1, "to_seq": 500 }
```
Response 200:
```json
{
  "verification_id": 17,
  "result": "FAIL",
  "checked_count": 500,
  "issues": [
    { "type": "modified",  "seq_id": 120, "detail": "curr_hash mismatch: stored 1ab7..., recomputed 77c0..." },
    { "type": "missing",   "seq_id": 245, "detail": "sequence gap: 244 -> 246" },
    { "type": "reordered", "seq_id": 301, "detail": "prev_hash does not match curr_hash of seq 300" }
  ],
  "incidents_created": [31, 32, 33],
  "verified_at": "2026-11-20T14:31:00Z"
}
```
`result` ∈ `PASS` | `FAIL`. Each issue creates an incident and sends a Telegram alert (console in SIMULATED mode).

### `GET /api/integrity/status` — auth: JWT

Response 200:
```json
{
  "status": "red",
  "last_result": "FAIL",
  "last_verified_at": "2026-11-20T14:31:00Z",
  "total_logs": 1234,
  "open_incidents": 3,
  "last_anchored_batch_id": 7
}
```
`status` ∈ `green` (last PASS, no open incidents) | `yellow` (not verified recently, or anchoring pending) | `red` (last FAIL or open critical incidents).

### `GET /api/incidents` — auth: JWT

Query: `status` (`open` | `resolved`), `type`, `page`, `page_size`.
Response 200:
```json
{
  "items": [
    {
      "id": 31,
      "type": "modified",
      "severity": "critical",
      "seq_id": 120,
      "description": "curr_hash mismatch: stored 1ab7..., recomputed 77c0...",
      "status": "open",
      "alert_channel": "console",
      "alert_sent": true,
      "created_at": "2026-11-20T14:31:00Z"
    }
  ],
  "page": 1, "page_size": 50, "total": 3
}
```
`type` ∈ `modified` | `missing` | `reordered` | `heartbeat_timeout` | `merkle_mismatch`.

### `POST /api/merkle/build` — auth: JWT

Request (optional range; default = all logs not yet in a batch):
```json
{ "from_seq": 1, "to_seq": 100 }
```
Response 200:
```json
{
  "batch_id": 7,
  "root": "c3d9...64 hex",
  "leaf_count": 100,
  "from_seq": 1,
  "to_seq": 100,
  "created_at": "2026-11-20T14:32:00Z"
}
```
Leaf = `SHA-256(0x00 || curr_hash_bytes)`, node = `SHA-256(0x01 || left || right)` (domain separation). Odd node at a level is paired with itself. Error 400 if no unbatched logs / empty range, 409 if the range overlaps an existing batch.

### `GET /api/merkle/{batch_id}` — auth: JWT

Response 200:
```json
{
  "batch_id": 7,
  "root": "c3d9...",
  "leaf_count": 100,
  "from_seq": 1,
  "to_seq": 100,
  "levels": [ ["leaf0", "leaf1", "..."], ["..."], ["c3d9..."] ],
  "anchored": true,
  "anchor_tx_hash": "0xabc...",
  "created_at": "2026-11-20T14:32:00Z"
}
```
Error 404 if batch not found.

### `GET /api/merkle/{batch_id}/proof/{seq_id}` — auth: JWT

Response 200:
```json
{
  "batch_id": 7,
  "seq_id": 42,
  "leaf": "1ab7...",
  "leaf_index": 41,
  "proof": [
    { "position": "right", "hash": "aa01..." },
    { "position": "left",  "hash": "bb02..." }
  ],
  "root": "c3d9..."
}
```
Error 404 if batch or seq_id not in batch.

### `POST /api/blockchain/anchor` — auth: JWT

Request:
```json
{ "batch_id": 7 }
```
Response 200:
```json
{
  "batch_id": 7,
  "onchain_batch_id": "6256315520342587137...",
  "root": "c3d9...",
  "mode": "SIMULATED",
  "chain_id": 15000,
  "tx_hash": "0x5e1f...",
  "block_number": 1234567,
  "block_timestamp": "2026-11-20T14:33:00Z",
  "contract_address": "0x...",
  "explorer_url": "https://orchard.quaiscan.io/tx/0x5e1f..."
}
```
Errors: 404 (no batch), 409 (already anchored), 503 (RPC unavailable in REAL mode). In SIMULATED mode `explorer_url` is `null`.
`onchain_batch_id` (decimal string of a uint256) is the key used in the contract: `(first 64 bits of genesis log curr_hash << 64) | batch_id`, so separate log databases never collide on one contract. Read it on-chain with `getAnchor(onchain_batch_id)`.

### `GET /api/blockchain/status` — auth: JWT

Response 200:
```json
{
  "mode": "SIMULATED",
  "chain_id": 15000,
  "connected": true,
  "contract_address": null,
  "latest_block": 1234570,
  "anchored_batches": 7,
  "last_anchor": { "batch_id": 7, "tx_hash": "0x5e1f...", "block_number": 1234567, "explorer_url": null }
}
```
The anchor wallet address may be shown; the private key is never returned.

### `POST /api/proof/verify` — auth: JWT

Recomputes the Merkle root from current DB logs and compares with the anchored root (on-chain in REAL mode, simulator ledger otherwise). Optionally verifies a single inclusion proof.

Request:
```json
{ "batch_id": 7, "seq_id": 42 }
```
Response 200:
```json
{
  "batch_id": 7,
  "result": "MATCH",
  "local_root": "c3d9...",
  "anchored_root": "c3d9...",
  "inclusion_proof_valid": true,
  "tx_hash": "0x5e1f...",
  "explorer_url": "https://orchard.quaiscan.io/tx/0x5e1f...",
  "note": "MATCH means the logs in this batch hash to the root anchored at block 1234567. It does not prove the events themselves occurred."
}
```
`result` ∈ `MATCH` | `MISMATCH` | `NOT_ANCHORED`. Leaves are **recomputed from log content** (not copied from stored hashes), and the log count must equal `leaf_count`, so content edits, full chain rewrites and tail truncation all give MISMATCH. If the DB records an anchor but none exists on-chain under its key, the result is MISMATCH. The response also includes `stored_root`, `leaf_count`, `logs_found`, `problems[]`, `onchain_batch_id`, `mode`.

### `GET /api/evidence/{batch_id}/json` — auth: JWT

Response 200 (`Content-Disposition: attachment; filename=evidence_batch_7.json`):
```json
{
  "schema_version": "1.0",
  "generated_at": "2026-11-20T14:35:00Z",
  "batch": { "batch_id": 7, "from_seq": 1, "to_seq": 100, "leaf_count": 100, "merkle_root": "c3d9..." },
  "logs": [ { "...SecurityLog..." } ],
  "hash_algorithm": "SHA-256",
  "canonicalization": "JSON, sorted keys, no whitespace, UTF-8",
  "proofs": { "42": [ { "position": "right", "hash": "aa01..." } ] },
  "anchor": { "mode": "SIMULATED", "chain_id": 15000, "tx_hash": "0x5e1f...", "block_number": 1234567, "block_timestamp": "...", "contract_address": null, "explorer_url": null },
  "verification": { "result": "MATCH", "verified_at": "2026-11-20T14:35:00Z" },
  "disclaimer": "Blockchain anchoring proves only that this Merkle root has not changed since it was anchored. It does not prove that the logged events occurred or that logs were accurate before anchoring."
}
```
The bundle is self-contained: chain and root can be re-verified offline from this JSON alone.

### `GET /api/evidence/{batch_id}/pdf` — auth: JWT

Response 200: `Content-Type: application/pdf`, `Content-Disposition: attachment; filename=evidence_batch_7.pdf`.
A certificate with batch info, Merkle root, tx hash, explorer URL, verification result, and the disclaimer text above.

### `WebSocket /ws/live?token=<jwt>`

Server → client messages (JSON, one per event):
```json
{ "type": "log",          "data": { "...SecurityLog..." } }
{ "type": "heartbeat",    "data": { "agent_id": "agent-win-01", "received_at": "..." } }
{ "type": "agent_status", "data": { "agent_id": "agent-win-01", "status": "offline" } }
{ "type": "incident",     "data": { "...Incident..." } }
{ "type": "integrity",    "data": { "status": "red", "last_result": "FAIL" } }
{ "type": "anchor",       "data": { "batch_id": 7, "tx_hash": "0x...", "mode": "SIMULATED" } }
```
Connection without a valid token is closed with code 1008 (policy violation).

---

## Internal API: quai-service (Node.js, `127.0.0.1:8787`, loopback only)

Code: `backend/blockchain/quai-service/` (`server.js`, `app.js`). The FastAPI backend is the only client (no auth header;
it binds to `127.0.0.1`). Python calls it through `QuaiServiceAnchorer`; Python never reads `CYPRUS1_PK`.
Start read-only: `node server.js`. Broadcasting requires `node server.js --allow-broadcast` (otherwise `/anchor` → 403).

### `GET /status`
```json
{ "mode": "REAL", "network": "Quai Orchard Cyprus-1", "chain_id": 15000, "broadcast_allowed": false,
  "contract_address": "0x00...", "connected": true, "rpc_chain_id": 15000, "wallet_address": "0x00...",
  "wallet_zone": "0x00", "contract_has_code": true, "latest_block": 8305618 }
```
`mode` is `SIMULATED` (and `connected` false) when `RPC_URL`, `CYPRUS1_PK` or `CONTRACT_ADDRESS` is missing.
`latest_block` is always the Cyprus-1 height. The private key is never returned.

### `POST /anchor`
Request: `{ "root": "<64 hex>", "batch_id": "<uint256 as decimal string>" }`
Response 200: `{ "tx_hash": "0x...", "block_number": 8305620, "block_timestamp": "2026-...Z", "explorer_url": "https://orchard.quaiscan.io/tx/0x..." }`
Order of checks: input (`400`) → broadcast allowed (`403`, no RPC call made) → RPC reachable and chain = `CHAIN_ID`,
wallet in Cyprus-1, contract has code (`503`) → not already anchored (`409`) → send. Body > 4 KB → `413`.

### `GET /anchor/{batch_id}` · `GET /anchor/{batch_id}/tx`
`{ "batch_id", "root", "timestamp", "block_timestamp", "submitter" }` / `{ "batch_id", "root", "tx_hash", "block_number",
"block_timestamp", "explorer_url" }` (from the `RootAnchored` event), or `404` when not anchored.

## Quai compatibility

See `documentation/QUAI_COMPATIBILITY.md` (Solidity 0.8.20 + evmVersion london / no PUSH0, Cyprus-1 zone addresses,
quais-only signing, offline metadata CID instead of IPFS, RPC pathing, Prime vs Cyprus-1 block height).

## Additional endpoints (beyond the original contract)

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/auth/login` | none | Dashboard JWT |
| `GET /api/chain?from_seq=&limit=` | JWT | Hash-chain links with `hash_valid` / `link_valid` (visualization) |
| `POST /api/incidents/resolve?target=` | JWT | Acknowledge open incidents (status only; logs never change) |
| `GET /api/merkle/batches` | JWT | List batches with anchor tx |
| `POST /api/demo/tamper` `{seq_id, kind: modify\|delete\|reorder}` | JWT | Attack a **sandbox copy**, verify it, record sandbox incidents (`target="sandbox"`) |
| `POST /api/demo/reset` | JWT | Resolve sandbox incidents, re-verify live chain |

## Change log

| Date | Step | Change |
|---|---|---|
| 2026-11-20 | 1 | Scaffold, venv (Python 3.12), pinned requirements, branches, contract. `websockets` pinned to 13.1 because `web3==7.6.1` requires `websockets<14`. |
| 2026-11-20 | 2 | SQLite + Postgres schemas, restricted `log_writer` role (verified on local Postgres 16). |
| 2026-11-20 | 3 | Agent + collector. Windows collector unverified (no Windows host). |
| 2026-11-20 | 4 | API core. Fixed race in agent auto-registration (concurrent first heartbeat + event -> 500) with `ON CONFLICT DO NOTHING`; regression test added. Added `requirements.lock.txt`. Dashboard login = `admin` + API_KEY (demo simplification). |
| 2026-11-20 | 5 | Hash chain view endpoint; NIST vectors. |
| 2026-11-20 | 6 | Verifier (modified/missing/reordered), incidents, alerts, sandbox-only tamper simulator + demo endpoints. |
| 2026-11-20 | 7 | Merkle tree with 0x00/0x01 domain separation (contract updated). |
| 2026-11-20 | 8 | LogAnchor.sol (write-once, owner-only), Hardhat tests, solcjs pinned (no compiler download). web3.py REAL path verified against a local Hardhat node; Amoy not reachable from build host. Fixed on-chain batch key collision across databases (namespaced `onchain_batch_id`). Schema: `blockchain_anchors.onchain_batch_id` added. |
| 2026-11-20 | 9 | JSON evidence bundle (self-contained, with all proofs + on-chain key), PDF certificate with disclaimer, stdlib-only offline verifier. Added pypdf==5.1.0 (tests). |
| 2026-11-20 | 10 | Next.js 14.2.35 dashboard (10 pages + login), mock mode, live WebSocket, tamper demo. Screenshots in documentation/screenshots. |
| 2026-11-20 | 11 | 6-scenario E2E test; route-coverage check found 2 untested routes (fixed); config unit tests added; coverage 88%. Added coverage==7.6.9. |
| 2026-11-20 | 12 | start.ps1 + start.sh, README per-key setup, OpenAPI export, ARCHITECTURE/API/DEMO docs. Clean-clone launch verified with start.sh; fixed 3 launcher bugs (stdout held open / wrong PID, port collision false positive, restart race). 6 scenarios passed through the dashboard. |
| 2026-11-20 | Q1 | Quai rebuild started from `main` (+ migration fix). `.env.example` = 10 Quai keys; config reads `RPC_URL`/`CYPRUS1_PK`/`CHAIN_ID=15000`/`CONTRACT_ADDRESS`; Quai keys never reach web3.py (simulator until quai-service in Step 8); `/api/health` blockchain badge now reflects the anchorer actually in use. `backend/blockchain/quai-service/` created. |
| 2026-11-20 | Q2 | Schema re-verified on SQLite + Postgres 16 (8 tables, unique seq_id, FKs, `log_writer` INSERT/SELECT only). Postgres column migration now tested. Quai anchors fit existing columns; DATABASE.md upgrade section. |
| 2026-11-20 | Q3 | Agent unchanged since 07fb8c8; re-verified live (HTTPS to real API: 8 events, 0 errors; wrong key -> 401; http to remote refused; heartbeat 0/10/20 s). Windows collector still unverified. |
| 2026-11-20 | Q4 | API core re-verified with real HTTPS requests (seq 1->2, 401, 422, logs, JWT 401, health shows truthful SIMULATED badge, wss live logs, agent online->delayed->offline + heartbeat_timeout incident/alert). Operator accepted Step 3 Windows-collector gap. |
| 2026-11-20 | Q5 | Hash chain re-verified (NIST vectors, 5-log chain via API, genesis 0*64, independent hashlib recompute, /api/chain all valid). Hashing code unchanged since 077e982. |
| 2026-11-20 | Q6 | Tamper detection re-verified live: clean PASS; modify@4, delete@6 (gap 5->7), reorder@8/9 detected on sandbox copies; 5 incidents + console alerts; original fingerprint unchanged. Code unchanged since 14deca7. |
| 2026-11-20 | Q7 | Merkle tree re-verified (hand-computed 4- and 3-leaf roots, odd counts 1/3/5, one-byte leaf/sibling change fails, endpoints + merkle_batches storage). Code unchanged since f3ff95e. |
| 2026-11-20 | Q8 | Quai Step 8 (simulator): LogAnchor 0.8.20/london (0 PUSH0), Hardhat cyprus1 config, quais deploy script (dry run default, --broadcast flag, zone + chain guards, offline metadata CID), Node quai-service (/status, /anchor, /anchor/:id[/tx], broadcast gate), Python QuaiServiceAnchorer, web3.py removed (lock 66 -> 36 packages), Orchard QuaiScan links. Live read-only checks against the real Orchard RPC. Network allowlist environment `silent` created (docs.qu.ai, orchard.rpc.quai.network, orchard.quaiscan.io). |
| 2026-11-20 | Q9 | Evidence bundle/PDF: Quai network name, Orchard QuaiScan tx + contract links, explorer_status (source not verified, no IPFS), Quai on-chain check instructions; PolygonScan wording removed. Re-verified live (downloads, fields, standalone offline verify VALID/INVALID, PDF disclaimer). |
