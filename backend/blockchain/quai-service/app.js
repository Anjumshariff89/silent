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

function withTimeout(promise, ms, what) {
  let timer;
  return Promise.race([
    promise,
    new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${what} timed out after ${ms} ms`)), ms); }),
  ]).finally(() => clearTimeout(timer));
}

/** Most specific error text: quais wraps transport/RPC failures as "could not coalesce error", the cause is inside. */
function errText(e) {
  if (!e) return "unknown error";
  const inner = (e.error && e.error.message) || (e.info && e.info.error && e.info.error.message) || (e.cause && e.cause.message);
  const outer = e.shortMessage || e.message;
  return String(inner && (!outer || /coalesce/i.test(outer)) ? inner : outer || e).slice(0, 200);
}

/**
 * deps: { config: {chainId: bigint, contractAddress, allowBroadcast, rpcConfigured, real, rpcTimeoutMs?},
 *         connect?: () => ({provider, wallet, contract}), provider?, wallet?, contract?, getZone, shard }
 * connect() builds a fresh RPC connection; it is called lazily and again after a failed RPC check
 * (quais gives up network detection permanently after a few retries, so a new provider is the reconnect).
 * Tests may inject provider/wallet/contract directly instead. Any of them is null when its key is not set.
 */
function createHandlers(deps) {
  const { config } = deps;
  const timeoutMs = config.rpcTimeoutMs || 10000;
  let conn = null;

  function current() {
    if (conn) return conn;
    conn = deps.connect ? deps.connect()
      : { provider: deps.provider || null, wallet: deps.wallet || null, contract: deps.contract || null };
    return conn;
  }
  function reconnectLater() {
    if (!deps.connect || !conn) return;
    try { if (conn.provider && conn.provider.destroy) conn.provider.destroy(); } catch { /* ignore */ }
    conn = null;
  }
  const rpc = (promise, what) => withTimeout(promise, timeoutMs, what);

  /** Verified chain id from the RPC, or the real error. Never a made-up value. */
  async function checkChain() {
    const { provider } = current();
    if (!provider) return { chain: null, error: "RPC_URL is not set in .env" };
    try {
      return { chain: (await rpc(provider.getNetwork(), "RPC chain id request")).chainId, error: null };
    } catch (e) {
      reconnectLater();
      return { chain: null, error: `RPC unreachable: ${errText(e)}` };
    }
  }

  function missing(needWallet) {
    const m = [];
    if (!config.rpcConfigured && !current().provider) m.push("RPC_URL");
    if (needWallet && !current().wallet) m.push("CYPRUS1_PK");
    if (!config.contractAddress) m.push("CONTRACT_ADDRESS");
    return m;
  }

  async function guards({ needWallet }) {
    const m = missing(needWallet);
    if (m.length) throw new HttpError(503, `quai-service cannot ${needWallet ? "anchor" : "read the contract"}: ${m.join(", ")} not set in .env`);
    const { chain, error } = await checkChain();
    if (chain === null) throw new HttpError(503, `Quai ${error}`);
    if (chain !== config.chainId) throw new HttpError(503, `RPC chain ${chain} != configured CHAIN_ID ${config.chainId}; refusing`);
    const { provider, wallet } = current();
    if (needWallet && deps.getZone(wallet.address) !== ZONE_CYPRUS1) {
      throw new HttpError(503, `wallet ${wallet.address} is not a Cyprus-1 (0x00) address`);
    }
    const code = await rpc(provider.getCode(config.contractAddress), "getCode");
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
      // mode = what is configured; connected/rpc_chain_id/latest_block = what the RPC actually answered.
      const mode = config.real ? "REAL" : (config.rpcConfigured || current().provider) ? "READ-ONLY" : "NOT CONFIGURED";
      const { wallet } = current();
      const out = { mode, network: "Quai Orchard Cyprus-1", chain_id: Number(config.chainId),
        broadcast_allowed: !!config.allowBroadcast, contract_address: config.contractAddress || null,
        connected: false, rpc_chain_id: null, wallet_address: wallet ? wallet.address : null,
        wallet_zone: wallet ? deps.getZone(wallet.address) : null, contract_has_code: null, latest_block: null,
        rpc_error: null, missing_for_anchoring: missing(true) };
      const { chain, error } = await checkChain();
      if (chain === null) return { ...out, rpc_error: error };
      out.rpc_chain_id = Number(chain);
      if (chain !== config.chainId) return { ...out, rpc_error: `RPC reports chain ${chain}, expected CHAIN_ID ${config.chainId}` };
      out.connected = true;
      const { provider } = current();
      try {
        // explicit zone: with a bare RPC host quais defaults getBlockNumber() to Prime, not Cyprus-1
        out.latest_block = Number(await rpc(provider.getBlockNumber(deps.shard), "getBlockNumber"));
      } catch (e) { out.rpc_error = `latest block: ${errText(e)}`; }
      if (config.contractAddress) {
        try { const c = await rpc(provider.getCode(config.contractAddress), "getCode"); out.contract_has_code = !!c && c !== "0x"; }
        catch (e) { out.rpc_error = `contract code: ${errText(e)}`; }
      }
      return out;
    },

    async anchor(body) {
      if (!body || typeof body.root !== "string" || !HEX64.test(body.root)) throw new HttpError(400, "root must be 64 hex chars");
      const batchId = parseBatchId(body.batch_id);
      if (!config.allowBroadcast) {
        throw new HttpError(403, "broadcasting is disabled: start quai-service with --allow-broadcast once the operator approved");
      }
      await guards({ needWallet: true });
      const { contract } = current();
      if (await contract.isAnchored(batchId)) throw new HttpError(409, `batch ${batchId} already anchored`);
      const root = "0x" + body.root.replace(/^0x/, "").toLowerCase();
      const tx = await contract.anchorRoot(root, batchId);
      const receipt = await tx.wait();
      if (!receipt || Number(receipt.status) !== 1) throw new HttpError(502, `anchor transaction failed: ${tx.hash}`);
      let ts = null;
      for (const log of receipt.logs || []) {
        try {
          const ev = contract.interface.parseLog(log);
          if (ev && ev.name === "RootAnchored") ts = ev.args.timestamp;
        } catch { /* not our event */ }
      }
      return { tx_hash: tx.hash, block_number: Number(receipt.blockNumber),
        block_timestamp: ts === null ? null : iso(ts), explorer_url: explorerTx(config.chainId, tx.hash) };
    },

    async getAnchor(batchIdStr) {
      const batchId = parseBatchId(batchIdStr);
      await guards({ needWallet: false });
      const [root, timestamp, submitter] = await rpc(current().contract.getAnchor(batchId), "getAnchor");
      if (BigInt(timestamp) === 0n) throw new HttpError(404, `batch ${batchId} not anchored`);
      return { batch_id: batchId.toString(), root: root.replace(/^0x/, "").toLowerCase(), timestamp: Number(timestamp),
        block_timestamp: iso(timestamp), submitter };
    },

    async findAnchorTx(batchIdStr) {
      const batchId = parseBatchId(batchIdStr);
      await guards({ needWallet: false });
      const { contract } = current();
      const events = await rpc(contract.queryFilter(contract.filters.RootAnchored(batchId)), "queryFilter");
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

module.exports = { createHandlers, createListener, HttpError, explorerTx, withTimeout };
