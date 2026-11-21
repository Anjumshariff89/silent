// quai-service entrypoint. Binds to 127.0.0.1 only; the FastAPI backend is the only client.
//   node server.js                    # read-only: /status and lookups work, /anchor returns 403
//   node server.js --allow-broadcast  # /anchor may send transactions (operator-approved deployments only)
"use strict";

const http = require("http");
const path = require("path");
const fs = require("fs");
require("dotenv").config({ path: path.join(__dirname, "..", "..", "..", ".env") });
const quais = require("quais");
const { createHandlers, createListener } = require("./app");

const PORT = Number(process.env.QUAI_SERVICE_PORT || 8787);
const HOST = "127.0.0.1";

function makeProvider(rpcUrl) {
  // RPC_URL ending in a zone path (.../cyprus1) is used as-is; a bare host needs quais pathing.
  const hasZonePath = /\/(cyprus|paxos|hydra)[1-3]\/?$/i.test(new URL(rpcUrl).pathname);
  return new quais.JsonRpcProvider(rpcUrl, undefined, { usePathing: !hasZonePath });
}

function build() {
  const { CHAIN_ID, CONTRACT_ADDRESS, QUAI_RPC_TIMEOUT_MS } = process.env;
  // QUAI_RPC_URL / QUAI_PRIVATE_KEY are accepted as alternative names for RPC_URL / CYPRUS1_PK.
  const RPC_URL = process.env.RPC_URL || process.env.QUAI_RPC_URL;
  const CYPRUS1_PK = process.env.CYPRUS1_PK || process.env.QUAI_PRIVATE_KEY;
  const config = {
    chainId: BigInt(CHAIN_ID || 15000),
    contractAddress: CONTRACT_ADDRESS || "",
    allowBroadcast: process.argv.includes("--allow-broadcast"),
    rpcConfigured: Boolean(RPC_URL),            // enough for live status: chain id + latest block
    real: Boolean(RPC_URL && CYPRUS1_PK && CONTRACT_ADDRESS),  // needed to anchor
    rpcTimeoutMs: Number(QUAI_RPC_TIMEOUT_MS || 10000),
  };
  const abi = JSON.parse(fs.readFileSync(path.join(__dirname, "LogAnchor.abi.json"), "utf8"));
  // Wallet object built once (the key stays inside it); each connect() binds it to a fresh provider.
  const baseWallet = CYPRUS1_PK ? new quais.Wallet(CYPRUS1_PK) : null;
  const connect = RPC_URL ? () => {
    const provider = makeProvider(RPC_URL);
    const wallet = baseWallet ? baseWallet.connect(provider) : null;
    const contract = CONTRACT_ADDRESS ? new quais.Contract(CONTRACT_ADDRESS, abi, wallet || provider) : null;
    return { provider, wallet, contract };
  } : () => ({ provider: null, wallet: baseWallet, contract: null });
  return { config, connect, walletAddress: baseWallet ? baseWallet.address : null,
    getZone: quais.getZoneForAddress, shard: quais.Shard.Cyprus1 };
}

if (require.main === module) {
  const deps = build();
  const server = http.createServer(createListener(createHandlers(deps)));
  server.listen(PORT, HOST, () => {
    console.log(`[quai-service] listening on http://${HOST}:${PORT} mode=${deps.config.real ? "REAL" : deps.config.rpcConfigured ? "READ-ONLY" : "NOT CONFIGURED"} ` +
      `chain=${deps.config.chainId} broadcast_allowed=${deps.config.allowBroadcast}` +
      (deps.walletAddress ? ` wallet=${deps.walletAddress}` : ""));
  });
}

module.exports = { build, makeProvider };
