const { expect } = require("chai");
const { ethers } = require("hardhat");
const { anyValue } = require("@nomicfoundation/hardhat-chai-matchers/withArgs");

describe("LogAnchor", function () {
  const ROOT = "0x" + "ab".repeat(32);
  let c, owner, other;

  beforeEach(async () => {
    [owner, other] = await ethers.getSigners();
    c = await (await ethers.getContractFactory("LogAnchor")).deploy();
  });

  it("anchors a root, emits event with timestamp, and stores it", async () => {
    const tx = await c.anchorRoot(ROOT, 1);
    const block = await ethers.provider.getBlock((await tx.wait()).blockNumber);
    await expect(tx).to.emit(c, "RootAnchored").withArgs(1, ROOT, block.timestamp, owner.address);
    const [root, ts, submitter] = await c.getAnchor(1);
    expect(root).to.equal(ROOT);
    expect(ts).to.equal(block.timestamp);
    expect(submitter).to.equal(owner.address);
    expect(await c.isAnchored(1)).to.equal(true);
    expect(await c.anchorCount()).to.equal(1n);
  });

  it("is write-once per batch id", async () => {
    await c.anchorRoot(ROOT, 7);
    await expect(c.anchorRoot("0x" + "cd".repeat(32), 7)).to.be.revertedWithCustomError(c, "AlreadyAnchored").withArgs(7);
    expect((await c.getAnchor(7))[0]).to.equal(ROOT);
  });

  it("rejects non-owner and empty root", async () => {
    await expect(c.connect(other).anchorRoot(ROOT, 2)).to.be.revertedWithCustomError(c, "NotOwner");
    await expect(c.anchorRoot(ethers.ZeroHash, 3)).to.be.revertedWithCustomError(c, "EmptyRoot");
  });

  it("returns zero values for an unknown batch", async () => {
    const [root, ts] = await c.getAnchor(999);
    expect(root).to.equal(ethers.ZeroHash);
    expect(ts).to.equal(0n);
    expect(await c.isAnchored(999)).to.equal(false);
  });

  it("supports many independent batches", async () => {
    for (let i = 1; i <= 3; i++) await c.anchorRoot(ethers.zeroPadValue(ethers.toBeHex(i), 32), i);
    expect(await c.anchorCount()).to.equal(3n);
    expect((await c.getAnchor(2))[0]).to.equal(ethers.zeroPadValue("0x02", 32));
    await expect(c.anchorRoot(ROOT, 4)).to.emit(c, "RootAnchored").withArgs(4, ROOT, anyValue, owner.address);
  });
});
