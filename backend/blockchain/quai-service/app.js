// quai-service request handling. Dependencies (provider, wallet, contract) are injected so the
// logic is testable without a network. The private key never leaves the quais.Wallet object.
"use strict";

const HEX64 = /^(0x)?[0-9a-fA-F]{64}$/;
const UINT = /^[0-9]{1,78}$/;
const UINT256_MAX = (1n << 256n) - 1n;
const ZONE_CYPRUS1 = "0x00";

class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function explorerTx(chainId, hash) {
  return chainId === 15000n ? `https://orchard.quaiscan.io/tx/${hash}` : chainId === 9n ? `https://quaiscan.io/tx/${hash}` : null;
}

function iso(seconds) {
  return new Date(Number(seconds) * 1000).toISOString().replace(".000Z", "Z");
}

/**
 * deps: { config: {chainId: bigint, contractAddress, allowBroadcast, real}, provider, wallet, contract, getZone }
 * In SIMULATED mode (keys missing) provider/wallet/contract may be null.
 */
function createHandlers(deps) {
  const { config } = deps;

  async function rpcChainId() {
    try { return (await deps.provider.getNetwork()).chainId; } catch { return null; }
  }

  async function guards({ needWallet }) {
    if (!config.real) throw new HttpError(503, "quai-service is in SIMULATED mode: RPC_URL, CYPRUS1_PK and CONTRACT_ADDRESS must be set");
    const chain = await rpcChainId();
    if (chain === null) throw new HttpError(503, "Quai RPC unreachable");
    if (chain !== config.chainId) throw new HttpError(503, `RPC chain ${chain} != configured CHAIN_ID ${config.chainId}; refusing`);
    if (needWallet && deps.getZone(deps.wallet.address) !== ZONE_CYPRUS1) {
      throw new HttpError(503, `wallet ${deps.wallet.address} is not a Cyprus-1 (0x00) address`);
    }
    const code = await deps.provider.getCode(config.contractAddress);
    if (!code || code === "0x") throw new HttpError(503, `no contract code at ${config.contractAddress} on chain ${chain}`);
  }

  function parseBatchId(v) {
    if (typeof v !== "string" || !UINT.test(v)) throw new HttpError(400, "batch_id must be a decimal uint256 string");
    const n = BigInt(v);
    if (n > UINT256_MAX) throw new HttpError(400, "batch_id exceeds uint256");
    return n;
  }

  return {
    async status() {
      const base = { mode: config.real ? "REAL" : "SIMULATED", network: "Quai Orchard Cyprus-1",
        chain_id: Number(config.chainId), broadcast_allowed: !!config.allowBroadcast,
        contract_address: config.contractAddress || null };
      if (!config.real) return { ...base, connected: false, rpc_chain_id: null, wallet_address: null, latest_block: null };
      const chain = await rpcChainId();
      let latest = null, hasCode = null;
      if (chain !== null) {
        // explicit zone: with a bare RPC host quais defaults getBlockNumber() to Prime, not Cyprus-1
        try { latest = Number(await deps.provider.getBlockNumber(deps.shard)); } catch { latest = null; }
        try { const c = await deps.provider.getCode(config.contractAddress); hasCode = !!c && c !== "0x"; } catch { hasCode = null; }
      }
      return { ...base, connected: chain === config.chainId, rpc_chain_id: chain === null ? null : Number(chain),
        wallet_address: deps.wallet.address, wallet_zone: deps.getZone(deps.wallet.address),
        contract_has_code: hasCode, latest_block: latest };
    },

    async anchor(body) {
      if (!body || typeof body.root !== "string" || !HEX64.test(body.root)) throw new HttpError(400, "root must be 64 hex chars");
      const batchId = parseBatchId(body.batch_id);
      if (!config.allowBroadcast) {
        throw new HttpError(403, "broadcasting is disabled: start quai-service with --allow-broadcast once the operator approved");
      }
      await guards({ needWallet: true });
      if (await deps.contract.isAnchored(batchId)) throw new HttpError(409, `batch ${batchId} already anchored`);
      const root = "0x" + body.root.replace(/^0x/, "").toLowerCase();
      const tx = await deps.contract.anchorRoot(root, batchId);
      const receipt = await tx.wait();
      if (!receipt || Number(receipt.status) !== 1) throw new HttpError(502, `anchor transaction failed: ${tx.hash}`);
      let ts = null;
      for (const log of receipt.logs || []) {
        try {
          const ev = deps.contract.interface.parseLog(log);
          if (ev && ev.name === "RootAnchored") ts = ev.args.timestamp;
        } catch { /* not our event */ }
      }
      return { tx_hash: tx.hash, block_number: Number(receipt.blockNumber),
        block_timestamp: ts === null ? null : iso(ts), explorer_url: explorerTx(config.chainId, tx.hash) };
    },

    async getAnchor(batchIdStr) {
      const batchId = parseBatchId(batchIdStr);
      await guards({ needWallet: false });
      const [root, timestamp, submitter] = await deps.contract.getAnchor(batchId);
      if (BigInt(timestamp) === 0n) throw new HttpError(404, `batch ${batchId} not anchored`);
      return { batch_id: batchId.toString(), root: root.replace(/^0x/, "").toLowerCase(), timestamp: Number(timestamp),
        block_timestamp: iso(timestamp), submitter };
    },

    async findAnchorTx(batchIdStr) {
      const batchId = parseBatchId(batchIdStr);
      await guards({ needWallet: false });
      const events = await deps.contract.queryFilter(deps.contract.filters.RootAnchored(batchId));
      if (!events.length) throw new HttpError(404, `no RootAnchored event for batch ${batchId}`);
      const ev = events[events.length - 1];
      return { batch_id: batchId.toString(), root: ev.args.root.replace(/^0x/, "").toLowerCase(), tx_hash: ev.transactionHash,
        block_number: Number(ev.blockNumber), block_timestamp: iso(ev.args.timestamp),
        explorer_url: explorerTx(config.chainId, ev.transactionHash) };
    },
  };
}

/** Node http request listener. Only JSON, small bodies, fixed routes. */
function createListener(handlers) {
  return async (req, res) => {
    const send = (status, obj) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(obj));
    };
    try {
      const url = new URL(req.url, "http://localhost");
      const m = url.pathname.match(/^\/anchor\/([0-9]+)(\/tx)?$/);
      if (req.method === "GET" && url.pathname === "/status") return send(200, await handlers.status());
      if (req.method === "GET" && m) return send(200, m[2] ? await handlers.findAnchorTx(m[1]) : await handlers.getAnchor(m[1]));
      if (req.method === "POST" && url.pathname === "/anchor") {
        let raw = "";
        for await (const chunk of req) {
          raw += chunk;
          if (raw.length > 4096) throw new HttpError(413, "body too large");
        }
        let body;
        try { body = JSON.parse(raw || "{}"); } catch { throw new HttpError(400, "invalid JSON"); }
        return send(200, await handlers.anchor(body));
      }
      return send(404, { detail: "not found" });
    } catch (e) {
      if (e instanceof HttpError) return send(e.status, { detail: e.message });
      // quais errors carry shortMessage; never include request bodies or env in errors
      return send(502, { detail: `quai error: ${String(e.shortMessage || e.message).slice(0, 200)}` });
    }
  };
}

module.exports = { createHandlers, createListener, HttpError, explorerTx };
