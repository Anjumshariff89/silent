# CLAUDE.md — Logs the Attacker Can't Erase (Quai Orchard edition)

Tamper-evident security logging: SHA-256 hash chains → Merkle trees → anchoring on **Quai Orchard Cyprus-1**
(chain ID 15000). Live state, API contract and step checklist: `PROJECT_STATE.md`. Quai findings:
`documentation/QUAI_COMPATIBILITY.md`.

## Non-negotiable rules

- **Blockchain claims:** an anchor proves only that the anchored commitment has not changed since anchoring.
  Never write or imply that it proves an event happened.
- **Secrets:** never print, log, echo, commit or paste any key or token (`API_KEY`, `JWT_SECRET`, `CYPRUS1_PK`,
  `TELEGRAM_BOT_TOKEN`, DB URLs with passwords). Never ask the user to paste keys in chat; they edit `.env` themselves.
  When checking `.env`, report only whether a variable is SET or empty.
- **No broadcast without approval:** never send a Quai transaction (deploy or anchor) until the user replies
  **"approve"**. First show: network, chain ID, wallet address (never the key), contract name, constructor args.
  Use `node scripts/deploy.js` (dry run) to produce that plan; `--broadcast` / `--allow-broadcast` only after approval.
- **Throwaway testnet wallet only. Synthetic data only. Never touch real system logs** (the Windows collector is read-only).
- **`.env.example` holds exactly these 10 lines** (enforced by `tests/test_step1_setup.py`):
  `MODE=real`, `API_KEY=`, `JWT_SECRET=`, `DATABASE_URL=sqlite:///./local.db`, `RPC_URL=`, `CYPRUS1_PK=`,
  `CHAIN_ID=15000`, `CONTRACT_ADDRESS=`, `TELEGRAM_BOT_TOKEN=`, `TELEGRAM_CHAT_ID=`.
- **Do not integrate:** Polygon, x402 Work, Hashference, AbuseIPDB, IPFS (no uploads), OpenTimestamps, Slack.
- **Pin every dependency** (exact versions; `requirements.txt` + `requirements.lock.txt`, npm `--save-exact`).
- Target platform is **Windows 11 / PowerShell**; give Windows-compatible commands to the user.

## Quai specifics (verified, see QUAI_COMPATIBILITY.md)

- Python never signs Quai transactions and never reads `CYPRUS1_PK`; no web3.py. All signing is in the Node.js
  `backend/blockchain/quai-service` (quais SDK), called by `QuaiServiceAnchorer` over `127.0.0.1:8787`.
- Solidity **0.8.20** with `evmVersion: "london"` (no PUSH0). The deploy script refuses bytecode containing PUSH0.
- The wallet address must be in **Cyprus-1** (prefix `0x00`); scripts refuse other keys.
- `quais` ContractFactory needs the metadata IPFS CID: it is extracted **offline** from the bytecode, never uploaded.
  Consequence: QuaiScan source verification is not available.
- `RPC_URL` may be `https://orchard.rpc.quai.network/cyprus1` (used as-is) or the bare host (quais pathing).
  Always query Cyprus-1 explicitly for block numbers.
- Explorer: `https://orchard.quaiscan.io` (testnet), `https://quaiscan.io` (mainnet, chain 9).

## Working protocol (from the user)

Each step: announce (3 lines) → build → run + write tests → fix failures yourself (stop and ask only for a secret,
a decision, or after 3 failed attempts; show the real error) → **VERIFICATION REPORT** in the fixed table format with
real command output → commit on the feature branch → merge to `main` only when Overall = PASS → update
`PROJECT_STATE.md` → **stop and wait for "go"** ("auto" = continue but still print every report). Never weaken a test
to make it pass; never write "should work".

Branches: `feature/log-collection` (Steps 1–4), `feature/tamper-detection` (5–7), `feature/blockchain` (8–9),
`feature/frontend` (10–12). `feature/quai-orchard` and the untracked `smart-contracts/quai/` folder are someone
else's earlier experiment: leave them untouched (the folder is excluded via `.git/info/exclude`).
Commit or push only when asked or when a hook requests it; scan staged changes for secrets first.

## Commands

```bash
.venv/bin/python -m pytest -q                       # Python tests (Windows: .\.venv\Scripts\python.exe -m pytest -q)
cd smart-contracts && npx hardhat test              # contract + bytecode tests (pinned solcjs 0.8.20, no download)
cd backend/blockchain/quai-service && npm test      # quai-service unit tests (no network)
cd frontend && npm run lint && npm run typecheck && npm run build
```

Optional: `PG_TEST_URL=postgresql://…` (throwaway DB) enables the Postgres tests. Live read-only Quai checks:
`QUAI_LIVE=1 node --test --test-force-exit test/live-readonly.test.js` in the quai-service folder (never broadcasts).
In this cloud container Node needs `NODE_USE_ENV_PROXY=1` to reach Quai hosts through the proxy; a Windows PC does not.

## Layout

`backend/` FastAPI (`main.py`, `app/`, `api/`, `agent/`, `crypto/`, `merkle/`, `blockchain/`, `database/`,
`integrations/`), `backend/blockchain/quai-service/` Node anchoring service, `smart-contracts/` Hardhat (`LogAnchor.sol`),
`frontend/` Next.js 14 + TS + Tailwind dashboard, `tests/` pytest, `documentation/` docs + screenshots.
