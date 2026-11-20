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
  const { RPC_URL, CYPRUS1_PK, CHAIN_ID, CONTRACT_ADDRESS } = process.env;
  const config = {
    chainId: BigInt(CHAIN_ID || 15000),
    contractAddress: CONTRACT_ADDRESS || "",
    allowBroadcast: process.argv.includes("--allow-broadcast"),
    real: Boolean(RPC_URL && CYPRUS1_PK && CONTRACT_ADDRESS),
  };
  if (!config.real) return { config, getZone: quais.getZoneForAddress, shard: quais.Shard.Cyprus1 };
  const abi = JSON.parse(fs.readFileSync(path.join(__dirname, "LogAnchor.abi.json"), "utf8"));
  const provider = makeProvider(RPC_URL);
  const wallet = new quais.Wallet(CYPRUS1_PK, provider);
  const contract = new quais.Contract(CONTRACT_ADDRESS, abi, wallet);
  return { config, provider, wallet, contract, getZone: quais.getZoneForAddress, shard: quais.Shard.Cyprus1 };
}

if (require.main === module) {
  const deps = build();
  const server = http.createServer(createListener(createHandlers(deps)));
  server.listen(PORT, HOST, () => {
    console.log(`[quai-service] listening on http://${HOST}:${PORT} mode=${deps.config.real ? "REAL" : "SIMULATED"} ` +
      `chain=${deps.config.chainId} broadcast_allowed=${deps.config.allowBroadcast}` +
      (deps.wallet ? ` wallet=${deps.wallet.address}` : ""));
  });
}

module.exports = { build, makeProvider };
