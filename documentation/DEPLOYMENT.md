# Deployment evidence (Quai Orchard)

Only facts that were actually observed are recorded here. Nothing has been broadcast yet: per the project
rules, no Quai transaction is sent until the operator reviews the dry-run plan and replies "approve".

## Status

| Item | Value | Evidence |
|---|---|---|
| Network | Quai Orchard Cyprus-1 (testnet) | `docs.qu.ai/llms.txt` |
| Chain ID | 15000 | RPC `quai_chainId` → `0x3a98`; live test `RPC chain 15000` |
| RPC | `https://orchard.rpc.quai.network/cyprus1` | live read-only tests (both URL forms) |
| Contract | `LogAnchor` (Solidity 0.8.20, evmVersion london, 0 PUSH0) | `npx hardhat test` → 9 passing |
| ABI path | `smart-contracts/artifacts/contracts/LogAnchor.sol/LogAnchor.json` (copy: `backend/blockchain/quai-service/LogAnchor.abi.json`) | `node scripts/export-abi.js` |
| Constructor arguments | none | contract source |
| Metadata CID (from bytecode, not uploaded) | `QmPDcfUDBXxDqzikTmGrnnw5zasFfY55JiQVcXN8eQyGaS` | dry run on 2026-11-20 |
| Deployer wallet | _not set_ (operator's Cyprus-1 address goes here; never the key) | — |
| Contract address | **not deployed** | — |
| Deploy tx hash | **not deployed** | — |
| Deploy block | — | — |
| First anchor tx hash | — | — |
| On-chain root = local root | **not verified** (needs a deployment) | — |
| Explorer status | **not checked** (nothing on chain yet). After deployment: transactions/events visible on Orchard QuaiScan; contract **source not verifiable** (no IPFS metadata upload, by requirement) | — |

## Dry-run evidence (2026-11-20, nothing sent)

Run against the real Orchard RPC with a freshly generated throwaway Cyprus-1 key holding 0 QUAI (not the operator's key):

```json
{
  "action": "DRY RUN (nothing sent)",
  "network": "Quai Orchard Cyprus-1",
  "rpc_url": "https://orchard.rpc.quai.network/cyprus1",
  "chain_id_expected": "15000",
  "chain_id_rpc": "15000",
  "wallet_zone": "0x00",
  "wallet_balance_quai": "0.0",
  "contract_name": "LogAnchor",
  "constructor_args": [],
  "metadata_cid_from_bytecode": "QmPDcfUDBXxDqzikTmGrnnw5zasFfY55JiQVcXN8eQyGaS",
  "push0_in_bytecode": false
}
```

Refusals also verified: non-Cyprus-1 key → "is not a Cyprus-1 address…", `CHAIN_ID=9` against Orchard →
"RPC chain 15000 != CHAIN_ID 9; refusing".

## How to fill this table

1. Operator sets `RPC_URL`, `CYPRUS1_PK` (throwaway Cyprus-1, funded from the faucet) in `.env`.
2. `cd smart-contracts; npx hardhat compile; node scripts/deploy.js` → review the plan → reply "approve".
3. `node scripts/deploy.js --broadcast` writes `smart-contracts/deployments/chain15000-LogAnchor.json`
   (address, deploy tx, block, ABI path, QuaiScan links). Copy those values here.
4. Set `CONTRACT_ADDRESS`, run `.\start.ps1 -AllowBroadcast`, anchor one batch, then record the anchor tx and the
   result of `POST /api/proof/verify` (on-chain root vs local root). Open the QuaiScan links and record what is visible.
