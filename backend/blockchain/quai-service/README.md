# quai-service (built in Step 8)

Node.js service that anchors Merkle roots on **Quai Orchard Cyprus-1** (chain ID 15000) with the
`quais` SDK. The Python backend calls it over local HTTP (`127.0.0.1` only); Python never holds or
uses the signing key for Quai, and does not use web3.py.

Planned endpoints (see the API contract in `PROJECT_STATE.md`):
- `GET  /status`  - network, chain ID, contract address, connectivity, latest block
- `POST /anchor`  - `{ "root": "<64 hex>", "batch_id": "<uint256 decimal>" }` -> tx hash, block, timestamp
- `GET  /anchor/:batchId` - read the anchored root back from the contract

Keys come from the project `.env` via `dotenv`: `RPC_URL`, `CYPRUS1_PK`, `CHAIN_ID`, `CONTRACT_ADDRESS`.
No transaction is ever broadcast until the operator explicitly approves (see the Step 8 protocol).
