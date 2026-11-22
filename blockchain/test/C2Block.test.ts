import { expect } from "chai";
import { ContractTransactionResponse, ContractTransactionReceipt } from "ethers";
import { ethers, network } from "hardhat";

// ---------------------------------------------------------------------------
// Functional, negative and randomized tests for C2BlockIncrementalExperiment,
// run against the real SupplyChainBaseline ledger.
//
// The contract does not recompute Bloom hashes: it validates membership against the
// ledger and applies the bitmaps the writer sends. These tests therefore pass explicit,
// small bitmaps (main size 8, summary size 16) so every expected counter can be written
// down by hand, and a randomized test compares the chain with an independent JS model.
// ---------------------------------------------------------------------------

const MAIN = 8;
const SUMMARY = 16;
const WORDS = Math.ceil(SUMMARY / 256);

type Fixture = Awaited<ReturnType<typeof deployFixture>>;

// ------------------------------- fixtures ----------------------------------

async function deployFixture(opts: { capacity?: number; maxProducts?: number } = {}) {
  const signers = await ethers.getSigners();
  const [admin, writer, other] = signers;
  const senders = signers.slice(3, 8); // extra WRITER accounts: several txs in one block

  const ledgerFactory = await ethers.getContractFactory("SupplyChainBaseline", admin);
  const ledger: any = await ledgerFactory.deploy();
  await ledger.waitForDeployment();
  const WRITER = await ledger.getFunction("WRITER")();
  for (const s of [writer, ...senders]) {
    await ledger.getFunction("grantRole")(WRITER, await s.getAddress());
  }

  const c2Factory = await ethers.getContractFactory("C2BlockIncrementalExperiment", admin);
  const c2: any = await c2Factory.deploy(
    await ledger.getAddress(), MAIN, SUMMARY, opts.capacity ?? 5, opts.maxProducts ?? 3,
    await writer.getAddress());
  await c2.waitForDeployment();
  return { ledger, c2, writer, other, senders, admin };
}

let opCounter = 0;
const opId = (name = "op") => ethers.id(`${name}:${opCounter++}`);
const key = (id: string) => ethers.keccak256(ethers.toUtf8Bytes(id));
const mask = (bits: number[]) => bits.reduce((m, b) => m | (1n << BigInt(b)), 0n);
const words = (bits: number[]) => {
  const w: bigint[] = new Array(WORDS).fill(0n);
  for (const b of bits) w[Math.floor(b / 256)] |= 1n << BigInt(b % 256);
  return w;
};
const ZERO_WORDS = new Array(WORDS).fill(0n);

function payloadFor(id: string, revision: number) {
  const payload = JSON.stringify({ product_id: id, revision });
  return { payload, digest: ethers.keccak256(ethers.toUtf8Bytes(payload)) };
}

async function ledgerInsert(f: Fixture, id: string): Promise<number> {
  const { payload, digest } = payloadFor(id, 1);
  await (await f.ledger.connect(f.writer).getFunction("insertProduct")(
    opId("ledger-insert"), id, payload, digest, 0)).wait();
  return currentBlock(f, id);
}

async function ledgerUpdate(f: Fixture, id: string, revision: number): Promise<number> {
  const { payload, digest } = payloadFor(id, revision);
  const version = await f.ledger.getFunction("getLatestVersionId")(id);
  await (await f.ledger.connect(f.writer).getFunction("updateProduct")(
    opId("ledger-update"), id, version, payload, digest)).wait();
  return currentBlock(f, id);
}

async function ledgerDelete(f: Fixture, id: string): Promise<void> {
  const version = await f.ledger.getFunction("getLatestVersionId")(id);
  await (await f.ledger.connect(f.writer).getFunction("deleteProduct")(
    opId("ledger-delete"), id, version)).wait();
}

async function currentBlock(f: Fixture, id: string): Promise<number> {
  const [, version] = await f.ledger.getFunction("getCurrentProduct")(id);
  return Number(version.sourceBlockNumber);
}

/** Insert several products into ONE ledger block (hardhat: explicit gas + distinct senders). */
async function ledgerInsertBatch(f: Fixture, ids: string[]): Promise<number> {
  if (ids.length > f.senders.length) throw new Error("not enough senders");
  await network.provider.send("evm_setAutomine", [false]);
  const txs: ContractTransactionResponse[] = [];
  try {
    for (let i = 0; i < ids.length; i++) {
      const { payload, digest } = payloadFor(ids[i], 1);
      txs.push(await f.ledger.connect(f.senders[i]).getFunction("insertProduct")(
        opId("ledger-batch"), ids[i], payload, digest, 0, { gasLimit: 1_500_000 }));
    }
    await network.provider.send("evm_mine");
  } finally {
    await network.provider.send("evm_setAutomine", [true]);
  }
  for (const tx of txs) await tx.wait();
  const blocks = await Promise.all(ids.map((id) => currentBlock(f, id)));
  expect(new Set(blocks).size, "batch must land in one block").to.equal(1);
  return blocks[0];
}

type Args = {
  op?: string; block: number; indexRev?: bigint; ledgerRev?: bigint;
  added?: string[]; removed?: string[]; mainMask?: bigint; words?: bigint[];
};

async function callArgs(f: Fixture, a: Args) {
  return [
    a.op ?? opId("c2"), a.block,
    a.indexRev ?? (await f.c2.getFunction("stateRevision")()),
    a.ledgerRev ?? (await f.ledger.getFunction("stateRevision")()),
    a.added ?? [], a.removed ?? [],
    a.mainMask ?? 0n, a.words ?? ZERO_WORDS,
  ];
}

async function updateBlock(f: Fixture, a: Args): Promise<ContractTransactionReceipt> {
  const args = await callArgs(f, a);
  const tx = await f.c2.connect(f.writer).getFunction("updateBlock")(...args);
  return (await tx.wait())!;
}

function writes(f: Fixture, receipt: ContractTransactionReceipt) {
  for (const log of receipt.logs) {
    let parsed;
    try { parsed = f.c2.interface.parseLog(log); } catch { continue; }
    if (parsed && parsed.name === "BlockUpdated") {
      return {
        main: Number(parsed.args.mainWrites), summary: Number(parsed.args.summaryWrites),
        added: Number(parsed.args.added), removed: Number(parsed.args.removed),
        blockNumber: Number(parsed.args.blockNumber),
        ledgerRevision: Number(parsed.args.productLedgerRevision),
        stateRevision: Number(parsed.args.stateRevision),
      };
    }
  }
  throw new Error("BlockUpdated event not found");
}

async function sync(f: Fixture) {
  return (await f.c2.connect(f.writer).getFunction("synchronizeProductLedger")(
    await f.c2.getFunction("stateRevision")(),
    await f.ledger.getFunction("stateRevision")())).wait();
}

const mainCounts = async (f: Fixture) =>
  [...(await f.c2.getFunction("getMainCounts")())].map(Number);

async function summaryRow(f: Fixture, position: number) {
  const all = Array.from({ length: SUMMARY }, (_, i) => i);
  return [...(await f.c2.getFunction("getSummaryCountsAt")([position], all))].map(Number);
}

async function summaryAt(f: Fixture, position: number, bit: number) {
  return Number(await f.c2.getFunction("getSummaryCount")(position, bit));
}

// ----------------------------- deployment ----------------------------------

describe("C2BlockIncrementalExperiment: deployment", function () {
  it("stores its configuration and starts fresh and empty", async function () {
    const f = await deployFixture();
    expect(await f.c2.mainSize()).to.equal(MAIN);
    expect(await f.c2.summarySize()).to.equal(SUMMARY);
    expect(await f.c2.blockCapacity()).to.equal(5);
    expect(await f.c2.maxProductsPerBlock()).to.equal(3);
    expect(await f.c2.wordCount()).to.equal(WORDS);
    expect(await f.c2.writer()).to.equal(await f.writer.getAddress());
    expect(await f.c2.productLedger()).to.equal(await f.ledger.getAddress());
    expect(await f.c2.stateRevision()).to.equal(0);
    expect(await f.c2.activeBlocks()).to.equal(0);
    expect(await f.c2.indexedProductCount()).to.equal(0);
    expect(await f.c2.isFresh()).to.equal(true);
    expect(await mainCounts(f)).to.deep.equal(new Array(MAIN).fill(0));
  });

  it("rejects invalid constructor parameters", async function () {
    const f = await deployFixture();
    const factory = await ethers.getContractFactory("C2BlockIncrementalExperiment");
    const ledger = await f.ledger.getAddress();
    const w = await f.writer.getAddress();
    const zero = ethers.ZeroAddress;
    await expect(factory.deploy(zero, 8, 16, 5, 3, w)).to.be.revertedWith("Invalid product ledger");
    await expect(factory.deploy(ledger, 0, 16, 5, 3, w)).to.be.revertedWith("Invalid main size");
    await expect(factory.deploy(ledger, 257, 16, 5, 3, w)).to.be.revertedWith("Invalid main size");
    await expect(factory.deploy(ledger, 8, 0, 5, 3, w)).to.be.revertedWith("Invalid summary size");
    await expect(factory.deploy(ledger, 8, 65537, 5, 3, w)).to.be.revertedWith("Invalid summary size");
    await expect(factory.deploy(ledger, 8, 16, 0, 3, w)).to.be.revertedWith("Invalid capacity");
    await expect(factory.deploy(ledger, 8, 16, 65536, 3, w)).to.be.revertedWith("Invalid capacity");
    await expect(factory.deploy(ledger, 8, 16, 5, 0, w)).to.be.revertedWith("Invalid block cap");
    await expect(factory.deploy(ledger, 8, 16, 5, 65, w)).to.be.revertedWith("Invalid block cap");
    await expect(factory.deploy(ledger, 8, 16, 5, 3, zero)).to.be.revertedWith("Invalid writer");
  });
});

// ------------------------------- functional --------------------------------

describe("C2BlockIncrementalExperiment: incremental updates", function () {
  it("adds the first product of a block and writes exactly its counters", async function () {
    const f = await deployFixture();
    const block = await ledgerInsert(f, "A");
    expect(await f.c2.isFresh()).to.equal(false); // ledger moved, index has not

    const receipt = await updateBlock(f, {
      block, added: ["A"], mainMask: mask([0, 1]), words: words([2, 5]),
    });
    const w = writes(f, receipt);
    expect(w).to.include({ main: 2, summary: 4, added: 1, removed: 0, blockNumber: block });

    expect(await mainCounts(f)).to.deep.equal([1, 1, 0, 0, 0, 0, 0, 0]);
    for (const p of [0, 1]) for (const b of [2, 5]) expect(await summaryAt(f, p, b)).to.equal(1);
    expect(await summaryAt(f, 0, 3)).to.equal(0);
    expect(await summaryAt(f, 2, 2)).to.equal(0);
    expect(await f.c2.activeBlocks()).to.equal(1);
    expect(await f.c2.indexedProductCount()).to.equal(1);
    expect(await f.c2.stateRevision()).to.equal(1);
    expect(await f.c2.blockOfProductPlusOne(key("A"))).to.equal(block + 1);

    const stored = await f.c2.getBlock(block);
    expect(stored.active).to.equal(true);
    expect(stored.mainMask).to.equal(mask([0, 1]));
    expect([...stored.bitWords]).to.deep.equal(words([2, 5]));
    expect([...stored.members]).to.deep.equal([key("A")]);
  });

  it("becomes fresh only after synchronizeProductLedger", async function () {
    const f = await deployFixture();
    const block = await ledgerInsert(f, "A");
    await updateBlock(f, { block, added: ["A"], mainMask: mask([0]), words: words([1]) });
    expect(await f.c2.isFresh()).to.equal(false);

    const receipt = await sync(f);
    expect(await f.c2.isFresh()).to.equal(true);
    expect(await f.c2.stateRevision()).to.equal(2);
    expect(await f.c2.indexedProductLedgerRevision()).to.equal(await f.ledger.stateRevision());
    await expect(receipt).to.emit(f.c2, "ProductLedgerSynchronized");
  });

  it("writes only the counters that change when a block gains a member", async function () {
    const f = await deployFixture();
    const block = await ledgerInsertBatch(f, ["A", "B"]);

    // A alone: main {0,1}, bits {2,5}
    await updateBlock(f, { block, added: ["A"], mainMask: mask([0, 1]), words: words([2, 5]) });
    // A + B: main {0,1,3}, bits {2,5,7}. Only the differences may be written.
    const r = writes(f, await updateBlock(f, {
      block, added: ["B"], mainMask: mask([0, 1, 3]), words: words([2, 5, 7]),
    }));
    // main: position 3 only. summary: bit 7 at positions 0 and 1 (2) + bits {2,5,7} at position 3 (3).
    expect(r.main).to.equal(1);
    expect(r.summary).to.equal(5);

    expect(await mainCounts(f)).to.deep.equal([1, 1, 0, 1, 0, 0, 0, 0]); // still ONE block
    expect(await summaryAt(f, 0, 7)).to.equal(1);
    expect(await summaryAt(f, 3, 5)).to.equal(1);
    expect(await summaryAt(f, 0, 2)).to.equal(1); // untouched
    expect(await f.c2.indexedProductCount()).to.equal(2);
    expect((await f.c2.getBlock(block)).members.length).to.equal(2);
  });

  it("undoes exactly those writes when the member is removed again", async function () {
    const f = await deployFixture();
    const block = await ledgerInsertBatch(f, ["A", "B"]);
    await updateBlock(f, { block, added: ["A"], mainMask: mask([0, 1]), words: words([2, 5]) });
    await updateBlock(f, { block, added: ["B"], mainMask: mask([0, 1, 3]), words: words([2, 5, 7]) });

    await ledgerDelete(f, "B");
    const r = writes(f, await updateBlock(f, {
      block, removed: ["B"], mainMask: mask([0, 1]), words: words([2, 5]),
    }));
    expect(r.main).to.equal(1);
    expect(r.summary).to.equal(5);
    expect(await mainCounts(f)).to.deep.equal([1, 1, 0, 0, 0, 0, 0, 0]);
    expect(await summaryAt(f, 0, 7)).to.equal(0);
    expect(await summaryAt(f, 3, 2)).to.equal(0);
    expect(await summaryAt(f, 0, 2)).to.equal(1);
    expect(await f.c2.indexedProductCount()).to.equal(1);
  });

  it("empties and deactivates a block when its last member is removed", async function () {
    const f = await deployFixture();
    const block = await ledgerInsert(f, "A");
    await updateBlock(f, { block, added: ["A"], mainMask: mask([0, 1]), words: words([2, 5]) });
    await ledgerDelete(f, "A");
    await updateBlock(f, { block, removed: ["A"] });

    expect(await mainCounts(f)).to.deep.equal(new Array(MAIN).fill(0));
    expect((await summaryRow(f, 0)).every((v) => v === 0)).to.equal(true);
    expect(await f.c2.activeBlocks()).to.equal(0);
    expect(await f.c2.indexedProductCount()).to.equal(0);
    expect(await f.c2.blockOfProductPlusOne(key("A"))).to.equal(0);
    const stored = await f.c2.getBlock(block);
    expect(stored.active).to.equal(false);
    expect(stored.mainMask).to.equal(0);
    expect([...stored.bitWords]).to.deep.equal(ZERO_WORDS);
    await sync(f);
    expect(await f.c2.isFresh()).to.equal(true);
  });

  it("keeps shared counters when only one of two overlapping blocks loses its product", async function () {
    const f = await deployFixture();
    const blockA = await ledgerInsert(f, "A");
    const blockB = await ledgerInsert(f, "B");
    await updateBlock(f, { block: blockA, added: ["A"], mainMask: mask([0, 1]), words: words([2, 5]) });
    await updateBlock(f, { block: blockB, added: ["B"], mainMask: mask([1, 2]), words: words([5, 6]) });
    expect(await mainCounts(f)).to.deep.equal([1, 2, 1, 0, 0, 0, 0, 0]);
    expect(await summaryAt(f, 1, 5)).to.equal(2);

    await ledgerDelete(f, "A");
    await updateBlock(f, { block: blockA, removed: ["A"] });
    expect(await mainCounts(f)).to.deep.equal([0, 1, 1, 0, 0, 0, 0, 0]);
    expect(await summaryAt(f, 1, 5)).to.equal(1); // B still contributes
    expect(await summaryAt(f, 1, 2)).to.equal(0);
    expect(await summaryAt(f, 2, 5)).to.equal(1);
    expect(await summaryAt(f, 2, 6)).to.equal(1);
  });

  it("moves a product between blocks: remove from the old block, then add to the new one", async function () {
    const f = await deployFixture();
    const oldBlock = await ledgerInsert(f, "P");
    await updateBlock(f, { block: oldBlock, added: ["P"], mainMask: mask([0, 1]), words: words([2, 5]) });
    await sync(f);

    const newBlock = await ledgerUpdate(f, "P", 2);
    expect(newBlock).to.be.greaterThan(oldBlock);

    // Adding first is refused: the contract still has P in the old block.
    await expect(f.c2.connect(f.writer).getFunction("updateBlock")(
      ...(await callArgs(f, { block: newBlock, added: ["P"], mainMask: mask([3]), words: words([7]) }))))
      .to.be.revertedWith("Product already indexed");

    await updateBlock(f, { block: oldBlock, removed: ["P"] });
    await updateBlock(f, { block: newBlock, added: ["P"], mainMask: mask([3]), words: words([7]) });
    await sync(f);

    expect(await mainCounts(f)).to.deep.equal([0, 0, 0, 1, 0, 0, 0, 0]);
    expect(await summaryAt(f, 3, 7)).to.equal(1);
    expect(await summaryAt(f, 0, 2)).to.equal(0);
    expect(await f.c2.blockOfProductPlusOne(key("P"))).to.equal(newBlock + 1);
    expect(await f.c2.activeBlocks()).to.equal(1);
    expect(await f.c2.isFresh()).to.equal(true);
  });

  it("can re-index a product after it was deleted and inserted again", async function () {
    const f = await deployFixture();
    const b1 = await ledgerInsert(f, "R");
    await updateBlock(f, { block: b1, added: ["R"], mainMask: mask([0]), words: words([1]) });
    await ledgerDelete(f, "R");
    await updateBlock(f, { block: b1, removed: ["R"] });

    const version = await f.ledger.getFunction("getLatestVersionId")("R");
    const { payload, digest } = payloadFor("R", 3);
    await (await f.ledger.connect(f.writer).getFunction("insertProduct")(
      opId("reinsert"), "R", payload, digest, version)).wait();
    const b2 = await currentBlock(f, "R");
    await updateBlock(f, { block: b2, added: ["R"], mainMask: mask([4]), words: words([9]) });
    expect(await mainCounts(f)).to.deep.equal([0, 0, 0, 0, 1, 0, 0, 0]);
    expect(await f.c2.blockOfProductPlusOne(key("R"))).to.equal(b2 + 1);
  });
});

// -------------------------------- limits -----------------------------------

describe("C2BlockIncrementalExperiment: limits", function () {
  it("refuses a block with more products than the per-block cap", async function () {
    const f = await deployFixture({ maxProducts: 3 });
    const block = await ledgerInsertBatch(f, ["A", "B", "C", "D"]);
    await updateBlock(f, { block, added: ["A"], mainMask: mask([0]), words: words([1]) });
    await updateBlock(f, { block, added: ["B"], mainMask: mask([0, 1]), words: words([1, 2]) });
    await updateBlock(f, { block, added: ["C"], mainMask: mask([0, 1, 2]), words: words([1, 2, 3]) });
    await expect(f.c2.connect(f.writer).getFunction("updateBlock")(
      ...(await callArgs(f, { block, added: ["D"], mainMask: mask([0, 1, 2, 3]), words: words([1, 2, 3, 4]) }))))
      .to.be.revertedWith("Block product cap exceeded");
    expect(await f.c2.indexedProductCount()).to.equal(3);
  });

  it("refuses a new block when the block capacity is full", async function () {
    const f = await deployFixture({ capacity: 2 });
    const b1 = await ledgerInsert(f, "A");
    const b2 = await ledgerInsert(f, "B");
    const b3 = await ledgerInsert(f, "C");
    await updateBlock(f, { block: b1, added: ["A"], mainMask: mask([0]), words: words([1]) });
    await updateBlock(f, { block: b2, added: ["B"], mainMask: mask([1]), words: words([2]) });
    await expect(f.c2.connect(f.writer).getFunction("updateBlock")(
      ...(await callArgs(f, { block: b3, added: ["C"], mainMask: mask([2]), words: words([3]) }))))
      .to.be.revertedWith("Capacity exceeded");
    expect(await f.c2.activeBlocks()).to.equal(2);

    // Freeing a block makes room again.
    await ledgerDelete(f, "A");
    await updateBlock(f, { block: b1, removed: ["A"] });
    await updateBlock(f, { block: b3, added: ["C"], mainMask: mask([2]), words: words([3]) });
    expect(await f.c2.activeBlocks()).to.equal(2);
  });
});

// ------------------------------ authorization ------------------------------

describe("C2BlockIncrementalExperiment: access and replay protection", function () {
  it("only the writer may update or synchronize", async function () {
    const f = await deployFixture();
    const block = await ledgerInsert(f, "A");
    const args = await callArgs(f, { block, added: ["A"], mainMask: mask([0]), words: words([1]) });
    await expect(f.c2.connect(f.other).getFunction("updateBlock")(...args))
      .to.be.revertedWith("Unauthorized writer");
    await expect(f.c2.connect(f.other).getFunction("synchronizeProductLedger")(
      await f.c2.stateRevision(), await f.ledger.stateRevision()))
      .to.be.revertedWith("Unauthorized writer");
  });

  it("rejects a reused operation ID, and a failed call does not consume its ID", async function () {
    const f = await deployFixture();
    const b1 = await ledgerInsert(f, "A");
    const b2 = await ledgerInsert(f, "B");
    const used = opId("replay");
    await updateBlock(f, { op: used, block: b1, added: ["A"], mainMask: mask([0]), words: words([1]) });
    await expect(f.c2.connect(f.writer).getFunction("updateBlock")(
      ...(await callArgs(f, { op: used, block: b2, added: ["B"], mainMask: mask([1]), words: words([2]) }))))
      .to.be.revertedWith("Operation already used");

    const failing = opId("failing");
    await expect(f.c2.connect(f.writer).getFunction("updateBlock")(
      ...(await callArgs(f, { op: failing, block: b2, added: ["B"], mainMask: 0n, words: ZERO_WORDS }))))
      .to.be.reverted; // empty main mask
    expect(await f.c2.usedOperationIds(failing)).to.equal(false);
    // ... so the same ID can be used for a corrected call.
    await updateBlock(f, { op: failing, block: b2, added: ["B"], mainMask: mask([1]), words: words([2]) });
  });

  it("rejects the empty operation ID", async function () {
    const f = await deployFixture();
    const block = await ledgerInsert(f, "A");
    await expect(f.c2.connect(f.writer).getFunction("updateBlock")(
      ...(await callArgs(f, { op: ethers.ZeroHash, block, added: ["A"], mainMask: mask([0]), words: words([1]) }))))
      .to.be.revertedWith("Empty operation ID");
  });

  it("rejects stale index and ledger revisions", async function () {
    const f = await deployFixture();
    const block = await ledgerInsert(f, "A");
    const rev = await f.c2.stateRevision();
    const lrev = await f.ledger.stateRevision();
    const base = { block, added: ["A"], mainMask: mask([0]), words: words([1]) };
    await expect(f.c2.connect(f.writer).getFunction("updateBlock")(
      ...(await callArgs(f, { ...base, indexRev: rev + 1n }))))
      .to.be.revertedWith("Index revision mismatch");
    await expect(f.c2.connect(f.writer).getFunction("updateBlock")(
      ...(await callArgs(f, { ...base, ledgerRev: lrev + 1n }))))
      .to.be.revertedWith("Product ledger revision mismatch");
  });
});

// ------------------------------- validation --------------------------------

describe("C2BlockIncrementalExperiment: input validation", function () {
  async function setup() {
    const f = await deployFixture();
    const block = await ledgerInsert(f, "Z");
    return { f, block };
  }
  const run = async (f: Fixture, a: Args) =>
    f.c2.connect(f.writer).getFunction("updateBlock")(...(await callArgs(f, a)));

  it("rejects a call that changes nothing", async function () {
    const { f, block } = await setup();
    await expect(run(f, { block })).to.be.revertedWith("No change");
  });

  it("rejects malformed bitmaps", async function () {
    const { f, block } = await setup();
    await expect(run(f, { block, added: ["Z"], mainMask: 0n, words: words([1]) }))
      .to.be.revertedWith("Empty main mask");
    await expect(run(f, { block, added: ["Z"], mainMask: mask([MAIN]), words: words([1]) }))
      .to.be.revertedWith("Main position out of range");
    await expect(run(f, { block, added: ["Z"], mainMask: mask([0]), words: words([SUMMARY]) }))
      .to.be.revertedWith("Summary position out of range");
    await expect(run(f, { block, added: ["Z"], mainMask: mask([0]), words: ZERO_WORDS }))
      .to.be.revertedWith("Empty summary filter");
    await expect(run(f, { block, added: ["Z"], mainMask: mask([0]), words: [...words([1]), 0n] }))
      .to.be.revertedWith("Invalid word count");
    expect(await f.c2.stateRevision()).to.equal(0); // nothing changed
  });

  it("rejects a non-empty filter for an empty block", async function () {
    const { f, block } = await setup();
    await updateBlock(f, { block, added: ["Z"], mainMask: mask([0]), words: words([1]) });
    await ledgerDelete(f, "Z");
    await expect(run(f, { block, removed: ["Z"], mainMask: mask([0]), words: words([1]) }))
      .to.be.revertedWith("Empty block must have empty filter");
  });

  it("validates membership against the ledger", async function () {
    const { f, block } = await setup();
    const ok = { mainMask: mask([0]), words: words([1]) };

    await expect(run(f, { block: block + 1, added: ["Z"], ...ok }))
      .to.be.revertedWith("Product not in this block");
    await expect(run(f, { block, added: ["GHOST"], ...ok }))
      .to.be.revertedWith("Unknown product");
    await expect(run(f, { block, removed: ["Z"] }))
      .to.be.revertedWith("Product not indexed in block");

    await updateBlock(f, { block, added: ["Z"], ...ok });
    await expect(run(f, { block, added: ["Z"], ...ok }))
      .to.be.revertedWith("Product already indexed");
    await expect(run(f, { block, removed: ["Z"] }))
      .to.be.revertedWith("Product still current in block");

    await ledgerDelete(f, "Z");
    await ledgerInsert(f, "Y");
    // A deleted product cannot be (re-)added.
    await updateBlock(f, { block, removed: ["Z"] });
    await expect(run(f, { block, added: ["Z"], ...ok }))
      .to.be.revertedWith("Product is not active");
  });

  it("refuses to synchronize while the index does not match the ledger", async function () {
    const f = await deployFixture();
    await ledgerInsert(f, "A"); // in the ledger, not in the index
    await expect(f.c2.connect(f.writer).getFunction("synchronizeProductLedger")(
      await f.c2.stateRevision(), await f.ledger.stateRevision()))
      .to.be.revertedWith("Active product count mismatch");
    await expect(f.c2.connect(f.writer).getFunction("synchronizeProductLedger")(
      (await f.c2.stateRevision()) + 1n, await f.ledger.stateRevision()))
      .to.be.revertedWith("Index revision mismatch");
    await expect(f.c2.connect(f.writer).getFunction("synchronizeProductLedger")(
      await f.c2.stateRevision(), (await f.ledger.stateRevision()) + 1n))
      .to.be.revertedWith("Product ledger revision mismatch");
  });
});

// ---------------------------------- views ----------------------------------

describe("C2BlockIncrementalExperiment: read functions", function () {
  it("bounds-check their arguments", async function () {
    const f = await deployFixture();
    await expect(f.c2.getMainCount(MAIN)).to.be.revertedWith("Main position out of range");
    await expect(f.c2.getSummaryCount(MAIN, 0)).to.be.revertedWith("Main position out of range");
    await expect(f.c2.getSummaryCount(0, SUMMARY)).to.be.revertedWith("Summary position out of range");
    await expect(f.c2.getSummaryCountsAt([], [0])).to.be.revertedWith("Empty selection");
    await expect(f.c2.getSummaryCountsAt([0], [])).to.be.revertedWith("Empty selection");
    await expect(f.c2.getSummaryCountsAt([MAIN], [0])).to.be.revertedWith("Main position out of range");
    await expect(f.c2.getSummaryCountsAt([0], [SUMMARY])).to.be.revertedWith("Summary position out of range");
  });

  it("returns summary counts as a row-major matrix", async function () {
    const f = await deployFixture();
    const block = await ledgerInsert(f, "A");
    await updateBlock(f, { block, added: ["A"], mainMask: mask([0, 2]), words: words([1, 4]) });
    const flat = [...(await f.c2.getSummaryCountsAt([0, 1, 2], [1, 4, 5]))].map(Number);
    expect(flat).to.deep.equal([
      1, 1, 0, // main position 0
      0, 0, 0, // main position 1
      1, 1, 0, // main position 2
    ]);
  });
});

// -------------------------- randomized model check -------------------------

describe("C2BlockIncrementalExperiment: randomized comparison with an independent model", function () {
  // Each product has a fixed contribution; a block's filter is the union of its members.
  const productMain = (n: number) => [n % MAIN, (n * 3 + 1) % MAIN];
  const productBits = (n: number) => [(n * 5) % SUMMARY, (n * 7 + 3) % SUMMARY, (n * 11 + 1) % SUMMARY];

  function blockFilter(members: number[]) {
    const m = new Set<number>(), b = new Set<number>();
    for (const n of members) {
      productMain(n).forEach((x) => m.add(x));
      productBits(n).forEach((x) => b.add(x));
    }
    return { main: [...m], bits: [...b] };
  }

  function expected(blocks: Map<number, number[]>) {
    const main = new Array(MAIN).fill(0);
    const summary = Array.from({ length: MAIN }, () => new Array(SUMMARY).fill(0));
    for (const members of blocks.values()) {
      const { main: ms, bits } = blockFilter(members);
      for (const p of ms) { main[p]++; for (const b of bits) summary[p][b]++; }
    }
    return { main, summary };
  }

  it("matches the model after every operation (insert / update / delete)", async function () {
    this.timeout(0);
    const f = await deployFixture({ capacity: 60, maxProducts: 10 });
    const blocks = new Map<number, number[]>(); // block -> product numbers
    const where = new Map<number, number>();    // product number -> block
    const revision = new Map<number, number>();
    let next = 0;
    let seed = 12345;
    const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
    const idOf = (n: number) => `RND-${n}`;

    async function apply(block: number, added: number[], removed: number[]) {
      const members = (blocks.get(block) ?? []).filter((m) => !removed.includes(m)).concat(added);
      if (members.length) blocks.set(block, members); else blocks.delete(block);
      const { main, bits } = blockFilter(members);
      await updateBlock(f, {
        block, added: added.map(idOf), removed: removed.map(idOf),
        mainMask: members.length ? mask(main) : 0n,
        words: members.length ? words(bits) : ZERO_WORDS,
      });
    }

    async function check(step: number) {
      const want = expected(blocks);
      expect(await mainCounts(f), `main counters, step ${step}`).to.deep.equal(want.main);
      for (let p = 0; p < MAIN; p++) {
        expect(await summaryRow(f, p), `summary row ${p}, step ${step}`).to.deep.equal(want.summary[p]);
      }
      expect(await f.c2.activeBlocks()).to.equal(blocks.size);
      expect(await f.c2.indexedProductCount()).to.equal(where.size);
      expect(await f.c2.isFresh()).to.equal(true);
    }

    for (let step = 0; step < 90; step++) {
      const active = [...where.keys()];
      const roll = active.length === 0 ? 0 : rnd();
      if (roll < 0.4) {
        // insert 1-3 products into one ledger block
        const count = 1 + Math.floor(rnd() * 3);
        const nums = Array.from({ length: count }, () => next++);
        const block = await ledgerInsertBatch(f, nums.map(idOf));
        for (const n of nums) { await apply(block, [n], []); where.set(n, block); revision.set(n, 1); }
      } else if (roll < 0.75) {
        const n = active[Math.floor(rnd() * active.length)];
        const oldBlock = where.get(n)!;
        revision.set(n, revision.get(n)! + 1);
        const newBlock = await ledgerUpdate(f, idOf(n), revision.get(n)!);
        await apply(oldBlock, [], [n]);
        await apply(newBlock, [n], []);
        where.set(n, newBlock);
      } else {
        const n = active[Math.floor(rnd() * active.length)];
        const oldBlock = where.get(n)!;
        await ledgerDelete(f, idOf(n));
        await apply(oldBlock, [], [n]);
        where.delete(n);
      }
      await sync(f);
      await check(step);
    }
  });
});