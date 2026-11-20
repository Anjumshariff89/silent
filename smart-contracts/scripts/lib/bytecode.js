// Offline bytecode helpers for Quai deployment. No network access.
"use strict";

const PUSH0 = 0x5f;

/** Walk EVM opcodes (skipping PUSH1..PUSH32 immediates) and return offsets of PUSH0 (0x5f). */
function findPush0(hex) {
  const code = Buffer.from(hex.replace(/^0x/, ""), "hex");
  const metaLen = metadataLength(code);
  const end = code.length - metaLen; // CBOR metadata at the end is data, not code
  const hits = [];
  for (let i = 0; i < end; i++) {
    const op = code[i];
    if (op === PUSH0) hits.push(i);
    if (op >= 0x60 && op <= 0x7f) i += op - 0x5f; // skip PUSHn data
  }
  return hits;
}

function metadataLength(code) {
  if (code.length < 2) return 0;
  const n = code.readUInt16BE(code.length - 2);
  return n + 2 <= code.length ? n + 2 : 0;
}

const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function base58(buf) {
  let n = BigInt("0x" + buf.toString("hex"));
  let out = "";
  while (n > 0n) { out = B58[Number(n % 58n)] + out; n /= 58n; }
  for (const b of buf) { if (b !== 0) break; out = "1" + out; }
  return out;
}

/**
 * Extract the metadata IPFS CIDv0 (Qm..., 46 chars) that solc embeds in the CBOR trailer of the
 * bytecode when `metadata.bytecodeHash = "ipfs"`. Computed by the compiler; nothing is uploaded.
 */
function extractMetadataCid(hex) {
  const code = Buffer.from(hex.replace(/^0x/, ""), "hex");
  const len = metadataLength(code);
  if (!len) throw new Error("no CBOR metadata trailer in bytecode");
  const cbor = code.subarray(code.length - len, code.length - 2);
  const key = Buffer.from("6469706673", "hex"); // CBOR text "ipfs"
  const at = cbor.indexOf(key);
  if (at < 0) throw new Error("metadata has no ipfs entry (set metadata.bytecodeHash='ipfs')");
  const head = cbor[at + key.length];
  if (head !== 0x58 || cbor[at + key.length + 1] !== 0x22) throw new Error("unexpected ipfs entry encoding");
  const multihash = cbor.subarray(at + key.length + 2, at + key.length + 2 + 34);
  if (multihash[0] !== 0x12 || multihash[1] !== 0x20) throw new Error("ipfs entry is not a sha2-256 multihash");
  const cid = base58(multihash);
  if (cid.length !== 46 || !cid.startsWith("Qm")) throw new Error(`bad CID ${cid}`);
  return cid;
}

module.exports = { findPush0, extractMetadataCid, base58 };
