"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("http");
const { createHandlers, createListener } = require("../app");

const ROOT = "ab".repeat(32);
const ADDR_CYPRUS1 = "0x0027aa00000000000000000000000000000000aa";
const ADDR_OTHER = "0x1a00000000000000000000000000000000000000";

function fakes(over = {}) {
  const sent = [];
  const anchored = new Map();
  const iface = { parseLog: (l) => (l.topic === "RootAnchored" ? { name: "RootAnchored", args: { timestamp: 1790000000n } } : null) };
  const contract = {
    interface: iface,
    isAnchored: async (id) => anchored.has(id),
    anchorRoot: async (root, id) => {
      sent.push({ root, id });
      anchored.set(id, root);
      return { hash: "0x" + "11".repeat(32), wait: async () => ({ status: 1, blockNumber: 4321n, logs: [{ topic: "RootAnchored" }] }) };
    },
    getAnchor: async (id) => (anchored.has(id) ? [anchored.get(id), 1790000000n, ADDR_CYPRUS1] : ["0x" + "00".repeat(32), 0n, "0x" + "00".repeat(20)]),
    filters: { RootAnchored: (id) => ({ id }) },
    queryFilter: async (f) => (anchored.has(f.id)
      ? [{ args: { root: anchored.get(f.id), timestamp: 1790000000n }, transactionHash: "0x" + "11".repeat(32), blockNumber: 4321 }] : []),
  };
  const deps = {
    config: { chainId: 15000n, contractAddress: "0x00aa000000000000000000000000000000000001", allowBroadcast: true, real: true },
    provider: { getNetwork: async () => ({ chainId: 15000n }), getCode: async () => "0x6080", getBlockNumber: async () => 99n },
    wallet: { address: ADDR_CYPRUS1 },
    contract,
    getZone: (a) => a.slice(0, 4).toLowerCase(),
    ...over,
  };
  return { deps, sent, h: createHandlers(deps) };
}

test("SIMULATED mode: status says so, anchor refuses", async () => {
  const h = createHandlers({ config: { chainId: 15000n, contractAddress: "", allowBroadcast: true, real: false }, getZone: () => "0x00" });
  const s = await h.status();
  assert.equal(s.mode, "SIMULATED"); assert.equal(s.chain_id, 15000); assert.equal(s.connected, false);
  await assert.rejects(h.anchor({ root: ROOT, batch_id: "1" }), { status: 503 });
});

test("input validation", async () => {
  const { h } = fakes();
  await assert.rejects(h.anchor({ root: "xyz", batch_id: "1" }), { status: 400 });
  await assert.rejects(h.anchor({ root: ROOT, batch_id: "-1" }), { status: 400 });
  await assert.rejects(h.anchor({ root: ROOT, batch_id: (1n << 256n).toString() }), { status: 400 });
});

test("broadcast disabled -> 403 and nothing is sent, no chain calls", async () => {
  let rpcCalls = 0;
  const { deps, sent } = fakes();
  deps.config.allowBroadcast = false;
  deps.provider.getNetwork = async () => { rpcCalls++; return { chainId: 15000n }; };
  await assert.rejects(createHandlers(deps).anchor({ root: ROOT, batch_id: "1" }), { status: 403 });
  assert.equal(sent.length, 0); assert.equal(rpcCalls, 0);
});

test("guards: chain mismatch, unreachable RPC, wrong zone, missing contract code", async () => {
  let f = fakes(); f.deps.provider.getNetwork = async () => ({ chainId: 9n });
  await assert.rejects(f.h.anchor({ root: ROOT, batch_id: "1" }), (e) => e.status === 503 && /chain 9/.test(e.message));
  f = fakes(); f.deps.provider.getNetwork = async () => { throw new Error("ECONNREFUSED"); };
  await assert.rejects(f.h.anchor({ root: ROOT, batch_id: "1" }), (e) => e.status === 503 && /unreachable/.test(e.message));
  f = fakes({ wallet: { address: ADDR_OTHER } });
  await assert.rejects(f.h.anchor({ root: ROOT, batch_id: "1" }), (e) => e.status === 503 && /Cyprus-1/.test(e.message));
  f = fakes(); f.deps.provider.getCode = async () => "0x";
  await assert.rejects(f.h.anchor({ root: ROOT, batch_id: "1" }), (e) => e.status === 503 && /no contract code/.test(e.message));
  assert.equal(f.sent.length, 0);
});

test("anchor success returns tx, block, event timestamp, Orchard QuaiScan link; second time 409", async () => {
  const { h, sent } = fakes();
  const r = await h.anchor({ root: ROOT.toUpperCase(), batch_id: "7" });
  assert.equal(r.tx_hash, "0x" + "11".repeat(32)); assert.equal(r.block_number, 4321);
  assert.equal(r.block_timestamp, "2026-09-21T14:13:20Z"); // = new Date(1790000000 * 1000)
  assert.equal(r.explorer_url, "https://orchard.quaiscan.io/tx/0x" + "11".repeat(32));
  assert.deepEqual(sent, [{ root: "0x" + ROOT, id: 7n }]);
  await assert.rejects(h.anchor({ root: ROOT, batch_id: "7" }), { status: 409 });
});

test("getAnchor / findAnchorTx", async () => {
  const { h } = fakes();
  await assert.rejects(h.getAnchor("5"), { status: 404 });
  await h.anchor({ root: ROOT, batch_id: "5" });
  const a = await h.getAnchor("5");
  assert.equal(a.root, ROOT); assert.equal(a.timestamp, 1790000000);
  const t = await h.findAnchorTx("5");
  assert.equal(t.tx_hash, "0x" + "11".repeat(32)); assert.equal(t.root, ROOT);
});

test("HTTP listener: routes, JSON errors, body limit", async () => {
  const { h } = fakes();
  const srv = http.createServer(createListener(h));
  await new Promise((r) => srv.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${srv.address().port}`;
  try {
    assert.equal((await (await fetch(`${base}/status`)).json()).mode, "REAL");
    let r = await fetch(`${base}/anchor`, { method: "POST", body: JSON.stringify({ root: ROOT, batch_id: "3" }) });
    assert.equal(r.status, 200);
    r = await fetch(`${base}/anchor`, { method: "POST", body: "{bad" }); assert.equal(r.status, 400);
    r = await fetch(`${base}/anchor`, { method: "POST", body: "x".repeat(5000) }); assert.equal(r.status, 413);
    assert.equal((await fetch(`${base}/anchor/3`)).status, 200);
    assert.equal((await fetch(`${base}/anchor/3/tx`)).status, 200);
    assert.equal((await fetch(`${base}/nope`)).status, 404);
  } finally { srv.close(); }
});
