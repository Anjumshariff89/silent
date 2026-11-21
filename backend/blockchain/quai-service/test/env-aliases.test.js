"use strict";
// QUAI_RPC_URL / QUAI_PRIVATE_KEY are accepted as alternative names for RPC_URL / CYPRUS1_PK (no network used).
const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("crypto");

test("QUAI_RPC_URL / QUAI_PRIVATE_KEY aliases configure the service; canonical names win", () => {
  const { build } = require("../server");  // loads ../../../.env first (never overrides existing env vars)
  const saved = { ...process.env };
  try {
    for (const k of ["RPC_URL", "CYPRUS1_PK", "QUAI_RPC_URL", "QUAI_PRIVATE_KEY", "CONTRACT_ADDRESS"]) delete process.env[k];
    assert.equal(build().config.rpcConfigured, false);
    process.env.QUAI_RPC_URL = "https://orchard.rpc.quai.network/cyprus1";
    process.env.QUAI_PRIVATE_KEY = "0x" + crypto.randomBytes(32).toString("hex");  // random throwaway, never funded
    const d = build();
    assert.equal(d.config.rpcConfigured, true);
    assert.match(d.walletAddress, /^0x[0-9a-fA-F]{40}$/);
    const fromAlias = d.walletAddress;
    process.env.CYPRUS1_PK = "0x" + crypto.randomBytes(32).toString("hex");
    assert.notEqual(build().walletAddress, fromAlias);  // CYPRUS1_PK takes precedence over the alias
  } finally {
    for (const k of Object.keys(process.env)) if (!(k in saved)) delete process.env[k];
    Object.assign(process.env, saved);
  }
});
