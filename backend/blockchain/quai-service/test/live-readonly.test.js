"use strict";
// Read-only checks against the real Quai Orchard RPC. Runs only with QUAI_LIVE=1. Never sends a transaction.
const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("crypto");
const quais = require("quais");
const { makeProvider } = require("../server");
const { createHandlers } = require("../app");

const LIVE = process.env.QUAI_LIVE === "1";
const URLS = ["https://orchard.rpc.quai.network/cyprus1", "https://orchard.rpc.quai.network"];

for (const url of URLS) {
  test(`live: ${url} reports chain 15000 and a block number`, { skip: !LIVE, timeout: 60000 }, async () => {
    const p = makeProvider(url);
    const net = await p.getNetwork();
    assert.equal(net.chainId, 15000n);
    assert.ok(Number(await p.getBlockNumber()) > 0);
  });
}

test("live: Cyprus-1 throwaway wallet zone check and broadcast stays blocked", { skip: !LIVE, timeout: 60000 }, async () => {
  let w;
  for (let i = 0; i < 20000 && !w; i++) { // grind a throwaway key (no funds, never used to send)
    const c = new quais.Wallet("0x" + crypto.randomBytes(32).toString("hex"));
    if (quais.getZoneForAddress(c.address) === quais.Zone.Cyprus1) w = c;
  }
  assert.ok(w, "could not grind a Cyprus-1 key");
  const provider = makeProvider(URLS[0]);
  assert.equal(await provider.getBalance(w.address), 0n);
  const h = createHandlers({ config: { chainId: 15000n, contractAddress: "0x0000000000000000000000000000000000000001",
    allowBroadcast: false, real: true }, provider, wallet: w.connect(provider), contract: null, getZone: quais.getZoneForAddress,
    shard: quais.Shard.Cyprus1 });
  const s = await h.status();
  assert.equal(s.connected, true); assert.equal(s.rpc_chain_id, 15000); assert.equal(s.wallet_zone, "0x00");
  await assert.rejects(h.anchor({ root: "ab".repeat(32), batch_id: "1" }), { status: 403 });
});

test("live: both RPC URL forms report the same Cyprus-1 block height", { skip: !LIVE, timeout: 60000 }, async () => {
  const [a, b] = await Promise.all(URLS.map((u) => makeProvider(u).getBlockNumber(quais.Shard.Cyprus1)));
  assert.ok(Math.abs(Number(a) - Number(b)) <= 3, `${a} vs ${b}`);
});
