# Logs the Attacker Can't Erase

Tamper-evident security logging: **SHA-256 hash chains**, **Merkle trees** and **blockchain anchoring** on
**Quai Orchard** (Cyprus-1 testnet, chain ID 15000), with a dark SOC dashboard.

> **What blockchain anchoring proves:** that an anchored Merkle root (a commitment to a batch of log hashes)
> has not changed since it was anchored.
> **What it does NOT prove:** that a logged event actually happened, that the log source was honest, or that logs
> were not altered *before* anchoring.

Every integration falls back to a simulator when its keys are empty, so the whole system runs with **zero keys**.
The dashboard shows **"Quai Orchard (REAL)"** or **"SIMULATED"** for anchoring, and REAL/SIMULATED for the others.

![Overview](documentation/screenshots/01-overview.png)

## Quick start (Windows 11, PowerShell)

Prerequisites: **Python 3.12** (python.org installer, with the `py` launcher) and **Node.js 20 LTS or newer**.

```powershell
git clone https://github.com/Anjumshariff89/silent.git
cd silent
.\start.ps1
```

`start.ps1` creates `.venv`, installs the pinned dependencies, copies `.env.example` to `.env` (SIMULATED mode),
installs the quai-service and dashboard packages, builds the dashboard, then starts four processes:

| Service | Address | What it does |
|---|---|---|
| quai-service (Node.js + quais) | `http://127.0.0.1:8787/status` | Only component that talks to Quai; read-only unless started with `-AllowBroadcast` |
| Backend (FastAPI) | `http://127.0.0.1:8000/docs` | API, hash chain, verification, Merkle, evidence |
| Log agent | (no port) | Sends Windows Security events (or synthetic ones) + heartbeats |
| Dashboard (Next.js) | `http://127.0.0.1:3000` | SOC dashboard |

- Login: `admin` / your `API_KEY` (in simulator mode with an empty key: `dev-local-api-key`)
- Stop: `.\start.ps1 -Stop` · Add the verifier/anchoring process: `.\start.ps1 -WithVerifier`
- If scripts are blocked: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
- Linux/macOS: `./start.sh` (same steps; `--verifier`, `--allow-broadcast`, `--stop`)

## Configuration (`.env`)

Edit `.env` yourself. It is git-ignored: never commit it, never paste keys into chats or tickets.
`.env.example` contains exactly these 10 settings:

| Variable | Default | Purpose |
|---|---|---|
| `MODE` | `simulator` | `real` refuses to start unless `API_KEY` and `JWT_SECRET` are set |
| `API_KEY` | *(empty → dev key in simulator)* | Agent → API key (`X-API-Key`) and dashboard password |
| `JWT_SECRET` | *(empty → random per start)* | Signs dashboard JWTs |
| `DATABASE_URL` | `sqlite:///./local.db` | SQLite, or Supabase Postgres |
| `RPC_URL` | empty | Quai Orchard Cyprus-1 RPC |
| `CYPRUS1_PK` | empty | **Throwaway** Cyprus-1 testnet private key (read only by the Node quai-service) |
| `CHAIN_ID` | `15000` | Quai Orchard; the quai-service refuses to sign if the RPC reports another chain |
| `CONTRACT_ADDRESS` | empty | Deployed `LogAnchor` contract on Cyprus-1 |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | empty | Incident alerts |

Generate the two local secrets (PowerShell):

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print('API_KEY=' + secrets.token_urlsafe(32)); print('JWT_SECRET=' + secrets.token_urlsafe(48))"
```

### 1. Quai Orchard (blockchain anchoring)

Use a **throwaway testnet wallet only**, never one holding real funds.

1. **Get a Cyprus-1 account.** Quai addresses are zone-specific: a Cyprus-1 address starts with `0x00`. Create an
   account in a Quai wallet such as **Pelagus** and choose the Cyprus-1 zone. A random or MetaMask key is almost never
   in Cyprus-1 (about 1 in 600), and the tools refuse such keys.
2. **Fund it** with test QUAI from `https://orchard.faucet.quai.network` (or `https://testnet.quaidrop.xyz/7263`).
3. **Fill `.env`** yourself: `RPC_URL=https://orchard.rpc.quai.network/cyprus1` (check on `docs.qu.ai`),
   `CYPRUS1_PK=0x…`, `CHAIN_ID=15000`.
4. **Compile, test and dry-run the deployment** (sends nothing):
   ```powershell
   cd smart-contracts; npm ci; npx hardhat test; node scripts/deploy.js
   ```
   The dry run prints the network, chain ID, your wallet address and zone, balance, contract name, constructor
   arguments (none) and the metadata hash read from the bytecode. It never prints the key.
5. **Deploy** only once you have checked that plan: `node scripts/deploy.js --broadcast`. It writes
   `smart-contracts/deployments/chain15000-LogAnchor.json` (address, tx, block, ABI path, QuaiScan links).
   Put the address in `.env` as `CONTRACT_ADDRESS=`.
6. **Run with anchoring enabled:** `.\start.ps1 -AllowBroadcast`. The badge shows **Quai Orchard (REAL)**.
   Anchors link to `https://orchard.quaiscan.io/tx/…`, and `POST /api/proof/verify` reads the root back from the
   contract (`getAnchor(onchain_batch_id)`). Without `-AllowBroadcast` the quai-service is read-only and anchoring
   returns 403.

Notes (details in [`documentation/QUAI_COMPATIBILITY.md`](documentation/QUAI_COMPATIBILITY.md)):
- Solidity **0.8.20** compiled with `evmVersion: london` (no PUSH0). The compiler is the pinned npm `solc`, so
  nothing is downloaded.
- Nothing is uploaded to IPFS. As a result, the contract source cannot be verified on QuaiScan; its transactions and
  events are still visible there.
- Python never signs Quai transactions and never reads `CYPRUS1_PK`; only the Node quai-service does.

### 2. Supabase Postgres (database)

1. Create a Supabase project → **SQL Editor** → run `backend/database/schema_postgres.sql`, then
   `backend/database/roles_postgres.sql` (set the role password inside the editor).
2. **Project Settings → Database → Connection string (URI)** → `DATABASE_URL=postgresql://…`
3. Restart. The **database** badge turns **REAL**. Details: [`documentation/DATABASE.md`](documentation/DATABASE.md).

### 3. Telegram (incident alerts)

1. Talk to **@BotFather** → `/newbot` → copy the token into `TELEGRAM_BOT_TOKEN=`.
2. Send any message to your bot, then open `https://api.telegram.org/bot<token>/getUpdates` in a browser and copy
   `message.chat.id` into `TELEGRAM_CHAT_ID=`.
3. Restart. The **telegram** badge turns **REAL**. If Telegram fails, alerts fall back to the console (the token is never logged).

### 4. Windows Event Log (log collection)

No key. On Windows with `pywin32` (installed from `requirements.txt` on Windows), the agent reads the **Security**
log events 4624/4634/4672/4673 **read-only**. Reading the Security log needs an **elevated** PowerShell. Without
pywin32 or rights, the agent falls back to the synthetic event simulator automatically.

### 5. Orchard QuaiScan (explorer links)

No key. Links are built from the tx hash and contract address (`https://orchard.quaiscan.io/tx/<hash>`,
`…/address/<contract>`) and shown on the Blockchain Explorer and Evidence pages for REAL anchors only.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest                       # 111 tests (Postgres tests skip unless PG_TEST_URL is set)
cd smart-contracts; npx hardhat test                       # 9 contract + bytecode tests
cd backend\blockchain\quai-service; npm test               # 7 quai-service tests (no network)
cd frontend; npm run lint; npm run typecheck; npm run build
```

Optional read-only checks against the real Orchard RPC (never sends a transaction):
`$env:QUAI_LIVE="1"; node --test --test-force-exit test/live-readonly.test.js` in `backend\blockchain\quai-service`.

## Verify evidence offline

```powershell
.\.venv\Scripts\python.exe -m backend.crypto.offline_verify evidence_batch_1.json
```

It uses only the Python standard library and checks every log hash, chain link, the Merkle root, every inclusion
proof, and that the root equals the anchored root.

## Documentation

- [Architecture and trust model](documentation/ARCHITECTURE.md)
- [API reference](documentation/API.md) · [OpenAPI spec](documentation/openapi.json) · full contract in [`PROJECT_STATE.md`](PROJECT_STATE.md)
- [Database](documentation/DATABASE.md) · [Quai compatibility report](documentation/QUAI_COMPATIBILITY.md)
- [Deployment evidence](documentation/DEPLOYMENT.md) · [2-minute demo script](documentation/DEMO_SCRIPT.md)
- [Screenshots](documentation/screenshots/)

## Known limitations

- The demo dashboard login is `admin` + `API_KEY` (one shared secret). Replace it with real user accounts before production.
- The hash chain alone cannot detect deletion of the newest logs or a full recompute of the chain. Anchoring covers
  this **only after** a batch is anchored.
- The simulated chain is a local JSON file, not a blockchain. Only REAL mode gives an external, independent anchor.
- Contract source is not verifiable on QuaiScan (no IPFS metadata upload, by requirement).
- Sequential `seq_id` relies on a per-process lock: run a single backend worker.
- `/api/logs` search uses `LIKE`. Fine for demo volumes, not for millions of rows.
