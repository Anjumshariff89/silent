# Logs the Attacker Can't Erase

Tamper-evident security logging: **SHA-256 hash chains**, **Merkle trees** and **blockchain anchoring** on
**Quai Orchard** (Cyprus-1 testnet, chain ID 15000), with a dark SOC dashboard.

> **What blockchain anchoring proves:** that an anchored Merkle root (a commitment to a batch of log hashes)
> has not changed since it was anchored.
> **What it does NOT prove:** that a logged event actually happened, that the log source was honest, or that logs
> were not altered *before* anchoring.

Everything runs in **real mode**: no mock data, no simulated chain, no synthetic events. Logs enter only through
`POST /api/logs/ingest` (the Windows agent, or `scripts/seed_logs.py` for labelled test logs). An integration whose
keys are empty is shown honestly as **NOT CONFIGURED** (Quai), **SQLITE** (database), **CONSOLE** (Telegram) or
**UNAVAILABLE** (Windows Event Log) and fails with a clear message instead of faking a result.

![Overview](documentation/screenshots/01-overview.png)

## Quick start (Windows 11, PowerShell)

Prerequisites: **Python 3.12** (python.org installer, with the `py` launcher) and **Node.js 20 LTS or newer**.

```powershell
git clone https://github.com/Anjumshariff89/silent.git
cd silent
.\run-dev.ps1 -Seed
```

`run-dev.ps1` is a wrapper around `start.ps1`. It creates `.venv`, installs the pinned dependencies, creates `.env`
from `.env.example` if it does not exist yet (with a freshly generated `API_KEY` and `JWT_SECRET`, never printed),
installs the quai-service and dashboard packages, builds the dashboard, starts four processes, checks `/health`, `/status` and `/login`, and with `-Seed` inserts 20 test
logs through the API, verifies the chain and builds a Merkle batch:

| Service | Address | What it does |
|---|---|---|
| quai-service (Node.js + quais) | `http://127.0.0.1:8787/status` | Only component that talks to Quai; read-only unless started with `-AllowBroadcast` |
| Backend (FastAPI) | `http://127.0.0.1:8000/docs` | API, hash chain, verification, Merkle, evidence |
| Log agent | (no port) | Sends real Windows Security events + heartbeats (needs an elevated PowerShell; otherwise it reports why and exits) |
| Dashboard (Next.js) | `http://127.0.0.1:3000` | SOC dashboard |

- Open **http://127.0.0.1:3000**. Login: `admin` / the `API_KEY` value in your `.env`.
- Stop: `.\run-dev.ps1 -Stop` · Restart: `.\run-dev.ps1 -Restart` · Other ports: `.\run-dev.ps1 -ApiPort 8100 -WebPort 3100`
- From Git Bash or cmd, call PowerShell with `-File` (never `-Command "..."` with nested quotes):
  `pwsh -NoProfile -ExecutionPolicy Bypass -File .\run-dev.ps1`
- More test logs at any time: `.\.venv\Scripts\python.exe scripts\seed_logs.py --count 20 --verify`
- Linux/macOS: `./start.sh` (same steps; `--verifier`, `--allow-broadcast`, `--stop`)

## Configuration (`.env`)

Edit `.env` yourself. It is git-ignored: never commit it, never paste keys into chats or tickets.
`.env.example` contains exactly these 13 settings:

| Variable | Default | Purpose |
|---|---|---|
| `MODE` | `real` | Refuses to start unless `API_KEY` and `JWT_SECRET` are set (`run-dev.ps1` generates them on first run) |
| `API_KEY` | *(generated)* | Agent → API key (`X-API-Key`) and dashboard password |
| `JWT_SECRET` | *(generated)* | Signs dashboard JWTs |
| `DATABASE_URL` | `sqlite:///./local.db` | SQLite, or Supabase Postgres |
| `RPC_URL` | empty | Quai Orchard Cyprus-1 RPC |
| `CYPRUS1_PK` | empty | **Throwaway** Cyprus-1 testnet private key (read only by the Node quai-service) |
| `CHAIN_ID` | `15000` | Quai Orchard; the quai-service refuses to sign if the RPC reports another chain |
| `CONTRACT_ADDRESS` | empty | Deployed `LogAnchor` contract on Cyprus-1 |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | empty | Incident alerts |
| `SUPABASE_URL` | empty | Supabase project URL: turns on Supabase sign-in (also used for the JWKS public keys) |
| `SUPABASE_JWT_SECRET` | empty | Legacy HS256 JWT secret of the project (empty for projects with asymmetric signing keys) |
| `FRONTEND_ORIGIN` | empty | Extra allowed CORS origin(s), comma-separated; `http://127.0.0.1:3000` and `localhost:3000` are always allowed |

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
6. **Run with anchoring enabled:** `.\run-dev.ps1 -AllowBroadcast`. The badge shows **Quai Orchard (REAL)**.
   Anchors link to `https://orchard.quaiscan.io/tx/…`, and `POST /api/proof/verify` reads the root back from the
   contract (`getAnchor(onchain_batch_id)`). Without `-AllowBroadcast` the quai-service is read-only and anchoring
   returns 403. With only `RPC_URL` set (the public endpoint needs **no API key**) the badge shows
   **Quai Orchard (READ-ONLY)**: `/status` reports the live, verified chain ID and Cyprus-1 latest block, and anchoring
   returns 503 naming the missing settings. Without `RPC_URL` the badge shows **NOT CONFIGURED**. If the RPC fails,
   `/status` shows `connected: false` with the real error in `rpc_error` (10 s timeout, fresh connection on the next
   request); if the RPC is unreachable it returns 502/503 and the batch stays
   unanchored (nothing is faked). Anchored batches show the tx hash with a **Verify** button (reads the root back).

Notes (details in [`documentation/QUAI_COMPATIBILITY.md`](documentation/QUAI_COMPATIBILITY.md)):
- Solidity **0.8.20** compiled with `evmVersion: london` (no PUSH0). The compiler is the pinned npm `solc`, so
  nothing is downloaded.
- Nothing is uploaded to IPFS. As a result, the contract source cannot be verified on QuaiScan; its transactions and
  events are still visible there.
- Python never signs Quai transactions and never reads `CYPRUS1_PK`; only the Node quai-service does.

### 2. Supabase (database + dashboard sign-in)

Supabase is optional: without it the app uses SQLite and the local `admin` + `API_KEY` login. With it, logs are stored
in Supabase Postgres and every dashboard user signs in with their own email + password (Supabase Auth). The backend
verifies each user's access token on every request; it never needs the Supabase **service_role** key (do not copy it
anywhere).

1. **Create the project:** https://supabase.com → *New project* → choose a name, a strong database password (keep it
   in a password manager) and a region near you.
2. **Create the tables + Row Level Security:** *SQL Editor* → *New query* → paste the whole file
   `supabase/migrations/20261121000000_silent_schema.sql` → *Run*. It is safe to run twice. RLS lets signed-in users
   **read** the shared tamper-evident log; anonymous visitors get nothing and nobody can write through the Supabase API
   (only the backend writes, through `DATABASE_URL`).
3. **Auth settings:** *Authentication → Sign In / Providers* → Email enabled. If *Confirm email* is on, new users must
   click the link in their inbox before signing in. *Authentication → URL Configuration* → *Site URL*
   `http://127.0.0.1:3000`. (Supabase's built-in mailer sends only a few emails per hour; add SMTP for more.)
4. **Copy the values yourself** (never paste them into chats or tickets):

   | Where in Supabase | File | Variable |
   |---|---|---|
   | *Project Settings → API* (or *Data API*): Project URL | `.env` **and** `frontend\.env.local` | `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL` |
   | *Project Settings → API Keys*: `anon` / publishable key | `frontend\.env.local` only | `NEXT_PUBLIC_SUPABASE_ANON_KEY` |
   | *Project Settings → JWT Keys*: **Legacy JWT secret** (only if the project still signs with it) | `.env` | `SUPABASE_JWT_SECRET` |
   | *Connect* → *Session pooler* URI (works over IPv4), with your DB password | `.env` | `DATABASE_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require` |

   Projects that use the newer asymmetric *JWT signing keys* need no secret: leave `SUPABASE_JWT_SECRET` empty and the
   backend checks tokens against `SUPABASE_URL/auth/v1/.well-known/jwks.json`.
5. **Create `frontend\.env.local`:** `Copy-Item frontend\.env.local.example frontend\.env.local`, then fill the two
   `NEXT_PUBLIC_SUPABASE_*` lines. Only public values belong there (they are shipped to the browser).
6. **Run:** `.\run-dev.ps1 -Restart`. It checks both files, refuses to start if Supabase is configured on only one
   side, rebuilds the dashboard when `.env.local` changed, and shows badges **database SUPABASE** and **auth SUPABASE**.
   Open http://127.0.0.1:3000 → *No account yet? Create one*.

Logs still arrive from the Windows agent / `scripts\seed_logs.py` with the `X-API-Key`; signed-in users can also
`POST /logs`. More: [`documentation/DATABASE.md`](documentation/DATABASE.md).

### 3. Telegram (incident alerts)

1. Talk to **@BotFather** → `/newbot` → copy the token into `TELEGRAM_BOT_TOKEN=`.
2. Send any message to your bot, then open `https://api.telegram.org/bot<token>/getUpdates` in a browser and copy
   `message.chat.id` into `TELEGRAM_CHAT_ID=`.
3. Restart. The **telegram** badge turns **REAL** (otherwise **CONSOLE**). If Telegram fails, alerts fall back to the console (the token is never logged).

### 4. Windows Event Log (log collection)

No key. On Windows with `pywin32` (installed from `requirements.txt` on Windows), the agent reads the **Security**
log events 4624/4634/4672/4673 **read-only**. Reading the Security log needs an **elevated** PowerShell. Without
pywin32 or rights, the agent does **not** invent events: it prints the reason and exits (badge **UNAVAILABLE**).
Use `scripts/seed_logs.py` for test logs; they are labelled `(seed)` with agent id `seed-script`.

### 5. Orchard QuaiScan (explorer links)

No key. Links are built from the tx hash and contract address (`https://orchard.quaiscan.io/tx/<hash>`,
`…/address/<contract>`) and shown on the Blockchain Explorer and Evidence pages for REAL anchors only.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest                       # Postgres tests skip unless PG_TEST_URL is set)
cd smart-contracts; npx hardhat test                       # 9 contract + bytecode tests
cd backend\blockchain\quai-service; npm test               # 7 quai-service tests (no network)
cd frontend; npm run lint; npm run typecheck; npm run build
```

Optional read-only checks against the real Orchard RPC (never sends a transaction):
`$env:QUAI_LIVE="1"; node --test --test-force-exit test/live-readonly.test.js` in `backend\blockchain\quai-service`.

## Troubleshooting

**"Port in use" / "Port 8000 is already in use"**
```powershell
Get-NetTCPConnection -LocalPort 8000,3000,8787 -State Listen | Select-Object LocalPort,OwningProcess
Get-Process -Id <OwningProcess>
```
If it is an earlier run of this project: `.\run-dev.ps1 -Stop` (or `-Restart`). The scripts only stop processes they
started themselves. If it is another program, close it or pick other ports: `.\run-dev.ps1 -ApiPort 8100 -WebPort 3100`
(the dashboard is rebuilt automatically to point at the new API port).

**"ERR_CONNECTION_REFUSED" / "connection refused" / "Failed to fetch" in the dashboard**
Nothing is listening on that port: the service did not start or crashed. Check:
```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Get-Content data\runtime_logs\backend.err.log -Tail 40
Get-Content data\runtime_logs\frontend.err.log -Tail 40
Get-Content data\runtime_logs\quai-service.err.log -Tail 40
```
Common causes: `.env` has `MODE=real` but an empty `API_KEY`/`JWT_SECRET` (the backend refuses to start; fill them
or delete `.env` and rerun to regenerate), the backend was started on another port than the dashboard was built for
(rerun `.\run-dev.ps1 -Restart`), or a firewall blocks `127.0.0.1`. Use `127.0.0.1`, not `localhost`, in URLs.

**Sign-in or every dashboard request fails with 401 / "Invalid or expired token" (Supabase)**
- `SUPABASE_URL` in `.env` must be exactly the project URL (no trailing path) and match `NEXT_PUBLIC_SUPABASE_URL`.
- HS256 projects: `SUPABASE_JWT_SECRET` must be the project's *Legacy JWT secret* (not the anon or service key).
- After editing `frontend\.env.local` run `.\run-dev.ps1 -Restart` (the dashboard is rebuilt automatically).
- `403 Local login is disabled`: Supabase sign-in is on, so use your email account, not `admin`.

**`/bin/sh: -c: line 1: unexpected EOF while looking for matching '"'`**
The script was launched from Git Bash as `pwsh -Command "..."` with nested quotes. Run it from PowerShell, or use
`pwsh -NoProfile -ExecutionPolicy Bypass -File .\run-dev.ps1`.

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
- Without Quai keys there is no external anchor at all (shown as NOT CONFIGURED); only the hash chain protects the logs.
- Contract source is not verifiable on QuaiScan (no IPFS metadata upload, by requirement).
- Sequential `seq_id` relies on a per-process lock: run a single backend worker.
- `/api/logs` search uses `LIKE`. Fine for demo volumes, not for millions of rows.
