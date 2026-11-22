import { expect } from "chai";
import { BaseContract, ContractTransactionResponse, Signer } from "ethers";
import { existsSync, writeFileSync } from "node:fs";
import { ethers, network } from "hardhat";

// ---------------------------------------------------------------------------
// Block-level C2 vs full-rebuild baseline (index maintenance gas only).
//
//   * Baseline : every mutation republishes the whole index. Bloom parameters are
//                recomputed from the product count, exactly like the Python rebuild.
//   * C2-block : one contribution per block; only the affected block filter(s) are
//                updated, writing only the counters whose value changes.
//
// N = active products, K = products per block. K > 1 is produced by mining several
// ledger inserts into ONE block (automine is switched off for the batch).
// ---------------------------------------------------------------------------

const SIZES = (process.env.C2_BLOCK_SIZES ?? "10,50,100").split(",").map(Number);
const BLOCK_SIZES = (process.env.C2_BLOCK_KS ?? "1,5,10").split(",").map(Number);

const MAIN_SIZE = 64;
const C2_SUMMARY_BITS = 192; // must equal BlockC2Manager.summary_size
const C2_WORDS = Math.ceil(C2_SUMMARY_BITS / 256);
const C2_HASH_COUNT = 7;
const BLOCK_CAPACITY = 200;
const MAX_PRODUCTS_PER_BLOCK = 10;
const TARGET_FPR_PPM = 10000;
const FPR = 0.01;

// ----------------------------- hashing helpers -----------------------------

function hashPositions(token: Uint8Array, sizeBits: number, hashCount: number): number[] {
  const digest = ethers.getBytes(ethers.keccak256(token));
  const first = BigInt(ethers.hexlify(digest.slice(0, 16)));
  const second = BigInt(ethers.hexlify(digest.slice(16))) | 1n;
  const positions = new Set<number>();
  for (let index = 0; index < hashCount; index++) {
    positions.add(Number((first + BigInt(index) * second) % BigInt(sizeBits)));
  }
  return [...positions];
}

// ------------------------------ baseline side ------------------------------

type BaselineParams = { mBits: number; hashCount: number; bytes: number };

function baselineParams(productCount: number): BaselineParams {
  const capacity = productCount * 2; // two tokens per product
  const bits = Math.ceil(-(capacity * Math.log(FPR)) / Math.log(2) ** 2);
  const mBits = Math.max(8, bits);
  const hashCount = Math.max(1, Math.round((mBits / capacity) * Math.log(2)));
  return { mBits, hashCount, bytes: Math.ceil(mBits / 8) };
}

type Product = {
  productId: string;
  revision: number;
  payload: string;
  digest: string;
  versionId: bigint;
  sourceBlockNumber: bigint;
};

function makePayload(productId: string, revision: number) {
  const payload = JSON.stringify({ product_id: productId, research_revision: revision });
  return { payload, digest: ethers.keccak256(ethers.toUtf8Bytes(payload)) };
}

function baselineFilter(product: Product, params: BaselineParams): string {
  const idToken = ethers.toUtf8Bytes(`product-id:${product.productId}`);
  const digestToken = ethers.concat([
    ethers.toUtf8Bytes("record-digest:"),
    ethers.getBytes(product.digest),
  ]);
  const packed = new Uint8Array(params.bytes);
  for (const token of [idToken, ethers.getBytes(digestToken)]) {
    for (const bit of hashPositions(token, params.mBits, params.hashCount)) {
      packed[Math.floor(bit / 8)] |= 1 << (bit % 8);
    }
  }
  return ethers.hexlify(Buffer.from(packed));
}

async function receiptGas(tx: ContractTransactionResponse): Promise<bigint> {
  const receipt = await tx.wait();
  if (!receipt || receipt.status !== 1) throw new Error("Research transaction failed");
  return receipt.gasUsed;
}

async function publishFullGeneration(
  contract: BaseContract,
  publisher: Signer,
  products: Product[],
): Promise<{ gas: bigint; txs: number }> {
  const params = baselineParams(products.length);
  const revision = await contract.getFunction("stateRevision")();
  let gas = await receiptGas(
    await contract.connect(publisher).getFunction("beginIndexGeneration")(
      revision, params.mBits, params.hashCount, TARGET_FPR_PPM, products.length, params.bytes,
    ),
  );
  let txs = 1;
  const generationId = (await contract.getFunction("nextGenerationId")()) - 1n;
  const chunk = Number(await contract.getFunction("MAX_FILTERS_PER_CHUNK")());
  const filters = products.map((p) => baselineFilter(p, params));

  for (let start = 0; start < products.length; start += chunk) {
    const slice = products.slice(start, start + chunk);
    gas += await receiptGas(
      await contract.connect(publisher).getFunction("uploadFilterChunk")(
        generationId, start,
        slice.map((p) => p.versionId),
        slice.map((p) => p.sourceBlockNumber),
        filters.slice(start, start + chunk),
      ),
    );
    txs++;
  }

  const summary = new Uint8Array(params.bytes);
  for (const f of filters) {
    const bytes = ethers.getBytes(f);
    for (let i = 0; i < summary.length; i++) summary[i] |= bytes[i];
  }
  gas += await receiptGas(
    await contract.connect(publisher).getFunction("uploadSummaryChunk")(
      generationId, 0, ethers.hexlify(summary),
    ),
  );
  txs++;
  gas += await receiptGas(
    await contract.connect(publisher).getFunction("finalizeIndexGeneration")(generationId),
  );
  txs++;
  expect(await contract.getFunction("isIndexFresh")()).to.equal(true);
  return { gas, txs };
}

// -------------------------------- C2 side ----------------------------------

function blockFilter(ids: string[]): { mainMask: bigint; words: bigint[] } {
  const words: bigint[] = new Array(C2_WORDS).fill(0n);
  let mainMask = 0n;
  for (const id of ids) {
    const token = ethers.toUtf8Bytes(`product-id:${id}`);
    for (const bit of hashPositions(token, C2_SUMMARY_BITS, C2_HASH_COUNT)) {
      words[Math.floor(bit / 256)] |= 1n << BigInt(bit % 256);
    }
    for (const p of hashPositions(ethers.toUtf8Bytes(id), MAIN_SIZE, C2_HASH_COUNT)) {
      mainMask |= 1n << BigInt(p);
    }
  }
  return { mainMask, words };
}

type C2Cost = { gas: bigint; txs: number; writes: number };

class BlockIndex {
  opCounter = 0;
  constructor(
    readonly c2: BaseContract,
    readonly ledger: BaseContract,
    readonly writer: Signer,
    /** block number -> ordered member ids (mirror of what the contract holds) */
    readonly blocks: Map<number, string[]>,
  ) {}

  async updateBlock(blockNumber: number, added: string[], removed: string[]): Promise<{ gas: bigint; writes: number }> {
    const members = this.blocks.get(blockNumber) ?? [];
    const next = [...members.filter((m) => !removed.includes(m)), ...added];
    const { mainMask, words } = blockFilter(next);
    const tx = await this.c2.connect(this.writer).getFunction("updateBlock")(
      ethers.id(`c2b-op:${this.opCounter++}`),
      blockNumber,
      await this.c2.getFunction("stateRevision")(),
      await this.ledger.getFunction("stateRevision")(),
      added,
      removed,
      next.length === 0 ? 0n : mainMask,
      next.length === 0 ? new Array(C2_WORDS).fill(0n) : words,
    );
    const receipt = await tx.wait();
    if (!receipt || receipt.status !== 1) throw new Error("updateBlock failed");
    let writes = 0;
    for (const log of receipt.logs) {
      let parsed;
      try { parsed = this.c2.interface.parseLog(log); } catch { continue; }
      if (parsed && parsed.name === "BlockUpdated") {
        writes = Number(parsed.args.mainWrites) + Number(parsed.args.summaryWrites);
      }
    }
    if (next.length === 0) this.blocks.delete(blockNumber);
    else this.blocks.set(blockNumber, next);
    return { gas: receipt.gasUsed, writes };
  }

  async sync(): Promise<bigint> {
    return receiptGas(
      await this.c2.connect(this.writer).getFunction("synchronizeProductLedger")(
        await this.c2.getFunction("stateRevision")(),
        await this.ledger.getFunction("stateRevision")(),
      ),
    );
  }

  /** Recompute main counters from block membership and compare with the chain. */
  async assertConsistent(): Promise<void> {
    const expected: bigint[] = new Array(MAIN_SIZE).fill(0n);
    let products = 0;
    for (const members of this.blocks.values()) {
      const { mainMask } = blockFilter(members);
      for (let p = 0; p < MAIN_SIZE; p++) if ((mainMask >> BigInt(p)) & 1n) expected[p]++;
      products += members.length;
    }
    const actual: bigint[] = [...(await this.c2.getFunction("getMainCounts")())];
    expect(actual.map(BigInt)).to.deep.equal(expected);
    expect(await this.c2.getFunction("activeBlocks")()).to.equal(BigInt(this.blocks.size));
    expect(await this.c2.getFunction("indexedProductCount")()).to.equal(BigInt(products));
    expect(await this.c2.getFunction("isFresh")()).to.equal(true);
  }
}

// ------------------------------ ledger helpers -----------------------------

async function mineBatch(sends: Array<() => Promise<ContractTransactionResponse>>) {
  await network.provider.send("evm_setAutomine", [false]);
  const txs: ContractTransactionResponse[] = [];
  try {
    for (const send of sends) txs.push(await send());
    await network.provider.send("evm_mine");
  } finally {
    await network.provider.send("evm_setAutomine", [true]);
  }
  for (const tx of txs) await receiptGas(tx);
}

/**
 * Insert `ids` into the ledger inside ONE block; returns the products and that block.
 * Hardhat keeps a second transaction from the SAME sender queued (nonce gap) and mines
 * only one per block, so each transaction of the batch uses a different WRITER account.
 */
async function insertIntoOneBlock(
  ledger: BaseContract, senders: Signer[], ids: string[], tag: string,
): Promise<{ products: Product[]; blockNumber: number }> {
  if (ids.length > senders.length) throw new Error("not enough batch senders");
  const drafts = ids.map((id) => ({ id, ...makePayload(id, 1) }));
  await mineBatch(
    drafts.map((d, i) => () =>
      ledger.connect(senders[i]).getFunction("insertProduct")(
        ethers.id(`ledger-insert:${tag}:${d.id}`), d.id, d.payload, d.digest, 0,
        // Hardhat's default tx gas is the whole block gas limit, which would force one
        // transaction per block. An explicit limit lets several share a block.
        { gasLimit: 1_500_000 },
      ) as Promise<ContractTransactionResponse>),
  );
  const products: Product[] = [];
  let blockNumber = -1;
  for (const d of drafts) {
    const versionId = await ledger.getFunction("getLatestVersionId")(d.id);
    const version = await ledger.getFunction("getVersion")(versionId);
    const sb = Number(version.sourceBlockNumber);
    if (blockNumber === -1) blockNumber = sb;
    expect(sb, "all products of a group must share one block").to.equal(blockNumber);
    products.push({ productId: d.id, revision: 1, payload: d.payload, digest: d.digest,
      versionId, sourceBlockNumber: version.sourceBlockNumber });
  }
  return { products, blockNumber };
}

async function deploy() {
  const signers = await ethers.getSigners();
  const [admin, writer, publisher] = signers;
  const batchSenders = signers.slice(3, 3 + MAX_PRODUCTS_PER_BLOCK);
  const ledgerFactory = await ethers.getContractFactory("SupplyChainBaseline", admin);
  const ledger = await ledgerFactory.deploy();
  await ledger.waitForDeployment();
  await ledger.getFunction("grantRole")(await ledger.getFunction("WRITER")(), await writer.getAddress());
  await ledger.getFunction("grantRole")(
    await ledger.getFunction("INDEX_PUBLISHER")(), await publisher.getAddress());
  for (const sender of batchSenders) {
    await ledger.getFunction("grantRole")(await ledger.getFunction("WRITER")(), await sender.getAddress());
  }

  const c2Factory = await ethers.getContractFactory("C2BlockIncrementalExperiment", admin);
  const c2 = await c2Factory.deploy(
    await ledger.getAddress(), MAIN_SIZE, C2_SUMMARY_BITS, BLOCK_CAPACITY,
    MAX_PRODUCTS_PER_BLOCK, await writer.getAddress());
  await c2.waitForDeployment();
  return { ledger, c2, writer, publisher, batchSenders };
}

// ---------------------------------- test -----------------------------------

type Row = Record<string, string | number>;

const VERBOSE = !!process.env.C2_BLOCK_VERBOSE;
const t0 = Date.now();
const log = (message: string) => {
  if (VERBOSE) console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s] ${message}`);
};

describe("C2 block-level research gas comparison", function () {
  it("compares full-rebuild publication with block-level counter updates", async function () {
    this.timeout(0);
    expect(network.name).to.equal("hardhat");
    const rows: Row[] = [];
    const measurements: Array<Record<string, unknown>> = [];

    for (const n of SIZES) {
      for (const k of BLOCK_SIZES) {
        if (k > MAX_PRODUCTS_PER_BLOCK) throw new Error("K exceeds the per-block cap");
        const { ledger, c2, writer, publisher, batchSenders } = await deploy();
        const blocks = new Map<number, string[]>();
        const index = new BlockIndex(c2, ledger, writer, blocks);
        const products: Product[] = [];
        const productBlock = new Map<string, number>();

        // ---- build the ledger: N products grouped K per block ----
        for (let start = 0; start < n; start += k) {
          const ids = [];
          for (let i = start; i < Math.min(n, start + k); i++) ids.push(`MED-${n}-${k}-${String(i).padStart(3, "0")}`);
          const { products: group, blockNumber } = await insertIntoOneBlock(ledger, batchSenders, ids, `init-${n}-${k}-${start}`);
          products.push(...group);
          for (const g of group) productBlock.set(g.productId, blockNumber);
        }

        log(`N=${n} K=${k}: ledger built (${products.length} products)`);
        // ---- initial index population ----
        const baselineInitial = await publishFullGeneration(ledger, publisher, products);
        let c2Initial: C2Cost = { gas: 0n, txs: 0, writes: 0 };
        const byBlock = new Map<number, string[]>();
        for (const p of products) {
          const b = productBlock.get(p.productId)!;
          byBlock.set(b, [...(byBlock.get(b) ?? []), p.productId]);
        }
        for (const [blockNumber, ids] of byBlock) {
          for (const id of ids) {
            const r = await index.updateBlock(blockNumber, [id], []);
            c2Initial = { gas: c2Initial.gas + r.gas, txs: c2Initial.txs + 1, writes: c2Initial.writes + r.writes };
          }
        }
        c2Initial = { ...c2Initial, gas: c2Initial.gas + (await index.sync()), txs: c2Initial.txs + 1 };
        log(`N=${n} K=${k}: initial index done`);
        await index.assertConsistent();

        // ---- DELETE one product of the first block ----
        const firstBlock = [...blocks.keys()][0];
        const deleteId = blocks.get(firstBlock)![0];
        const deleteProduct = products.find((p) => p.productId === deleteId)!;
        await receiptGas(await ledger.connect(writer).getFunction("deleteProduct")(
          ethers.id(`ledger-delete:${n}-${k}`), deleteId, deleteProduct.versionId));
        products.splice(products.indexOf(deleteProduct), 1);
        productBlock.delete(deleteId);
        log('delete: ledger done');
        const baselineDelete = await publishFullGeneration(ledger, publisher, products);
        const dr = await index.updateBlock(firstBlock, [], [deleteId]);
        const c2Delete: C2Cost = { gas: dr.gas + (await index.sync()), txs: 2, writes: dr.writes };
        await index.assertConsistent();

        // ---- UPDATE one product: leaves its block, lands in a NEW block ----
        const sourceBlock = [...blocks.keys()][blocks.size > 1 ? 1 : 0];
        const updateId = blocks.get(sourceBlock)![0];
        const updateProduct = products.find((p) => p.productId === updateId)!;
        const upd = makePayload(updateId, 2);
        await receiptGas(await ledger.connect(writer).getFunction("updateProduct")(
          ethers.id(`ledger-update:${n}-${k}`), updateId, updateProduct.versionId, upd.payload, upd.digest));
        const newVersionId = await ledger.getFunction("getLatestVersionId")(updateId);
        const newVersion = await ledger.getFunction("getVersion")(newVersionId);
        const movedBlock = Number(newVersion.sourceBlockNumber);
        updateProduct.revision = 2;
        updateProduct.payload = upd.payload;
        updateProduct.digest = upd.digest;
        updateProduct.versionId = newVersionId;
        updateProduct.sourceBlockNumber = newVersion.sourceBlockNumber;
        productBlock.set(updateId, movedBlock);
        const baselineUpdate = await publishFullGeneration(ledger, publisher, products);
        const ur1 = await index.updateBlock(sourceBlock, [], [updateId]);
        const ur2 = await index.updateBlock(movedBlock, [updateId], []);
        const c2Update: C2Cost = { gas: ur1.gas + ur2.gas + (await index.sync()), txs: 3, writes: ur1.writes + ur2.writes };
        await index.assertConsistent();

        // ---- INSERT one new product in its own block ----
        const insertId = `MED-${n}-${k}-NEW`;
        const { products: fresh, blockNumber: newBlock } = await insertIntoOneBlock(
          ledger, batchSenders, [insertId], `new-${n}-${k}`);
        products.push(...fresh);
        const baselineInsert = await publishFullGeneration(ledger, publisher, products);
        const ir = await index.updateBlock(newBlock, [insertId], []);
        const c2Insert: C2Cost = { gas: ir.gas + (await index.sync()), txs: 2, writes: ir.writes };
        await index.assertConsistent();

        const add = (op: string, b: { gas: bigint; txs: number }, c: C2Cost) => {
          rows.push({
            N: n, K: k, operation: op,
            baseline_gas: Number(b.gas), baseline_txs: b.txs,
            c2_gas: Number(c.gas), c2_txs: c.txs, c2_counter_writes: c.writes,
            c2_over_baseline: Number((Number(c.gas) / Number(b.gas)).toFixed(3)),
          });
        };
        add("initial", baselineInitial, c2Initial);
        add("delete", baselineDelete, c2Delete);
        add("update", baselineUpdate, c2Update);
        add("insert", baselineInsert, c2Insert);

        measurements.push({
          active_products: n, products_per_block: k, blocks: blocks.size,
          initial: { baseline_gas: baselineInitial.gas.toString(), baseline_txs: baselineInitial.txs,
            c2_gas: c2Initial.gas.toString(), c2_txs: c2Initial.txs, c2_counter_writes: c2Initial.writes },
          delete: { baseline_gas: baselineDelete.gas.toString(), baseline_txs: baselineDelete.txs,
            c2_gas: c2Delete.gas.toString(), c2_txs: c2Delete.txs, c2_counter_writes: c2Delete.writes },
          update: { baseline_gas: baselineUpdate.gas.toString(), baseline_txs: baselineUpdate.txs,
            c2_gas: c2Update.gas.toString(), c2_txs: c2Update.txs, c2_counter_writes: c2Update.writes },
          insert: { baseline_gas: baselineInsert.gas.toString(), baseline_txs: baselineInsert.txs,
            c2_gas: c2Insert.gas.toString(), c2_txs: c2Insert.txs, c2_counter_writes: c2Insert.writes },
          comparison_scope: "index maintenance only; ledger mutation gas excluded",
        });
      }
    }

    console.table(rows);

    const outputPath = process.env.C2_BLOCK_GAS_OUTPUT;
    if (outputPath) {
      if (existsSync(outputPath)) throw new Error(`Refusing to overwrite existing gas report: ${outputPath}`);
      writeFileSync(
        outputPath,
        `${JSON.stringify({
          network: network.name, main_size: MAIN_SIZE, c2_summary_bits: C2_SUMMARY_BITS,
          c2_hash_count: C2_HASH_COUNT, max_products_per_block: MAX_PRODUCTS_PER_BLOCK,
          baseline: "full rebuild, parameters recomputed per product count",
          measurements,
        }, null, 2)}\n`,
        { encoding: "utf-8", flag: "wx" },
      );
    }
  });
});