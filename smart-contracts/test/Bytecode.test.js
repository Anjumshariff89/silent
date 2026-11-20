const { expect } = require("chai");
const { artifacts } = require("hardhat");
const { findPush0, extractMetadataCid, base58 } = require("../scripts/lib/bytecode");

describe("Quai bytecode compatibility", function () {
  it("compiled LogAnchor (init + runtime) contains no PUSH0 opcode", async () => {
    const art = await artifacts.readArtifact("LogAnchor");
    expect(findPush0(art.bytecode)).to.deep.equal([]);
    expect(findPush0(art.deployedBytecode)).to.deep.equal([]);
  });

  it("detects PUSH0 when present and ignores 0x5f inside PUSH data", () => {
    expect(findPush0("0x5f00")).to.deep.equal([0]);              // PUSH0, STOP
    expect(findPush0("0x605f00")).to.deep.equal([]);             // PUSH1 0x5f, STOP
    expect(findPush0("0x6000605f5f")).to.deep.equal([4]);        // PUSH1 00, PUSH1 5f, PUSH0
  });

  it("extracts the 46-char metadata CID from bytecode, offline", async () => {
    const art = await artifacts.readArtifact("LogAnchor");
    const cid = extractMetadataCid(art.bytecode);
    expect(cid).to.match(/^Qm[1-9A-HJ-NP-Za-km-z]{44}$/);
    expect(extractMetadataCid(art.deployedBytecode)).to.equal(cid);
  });

  it("base58 matches a known CIDv0 vector", () => {
    // sha256 multihash of the empty string -> well-known CIDv0 of 0-byte raw block digest
    const mh = Buffer.from("1220e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "hex");
    expect(base58(mh)).to.equal("QmdfTbBqBPQ7VNxZEYEj14VmRuZBkqFbiwReogJgS1zR1n");
  });
});
