import { expect } from "chai";
import { BaseContract, ContractTransactionResponse, Signer } from "ethers";
import { existsSync, writeFileSync } from "node:fs";
import { ethers, network } from "hardhat";

const CAPACITY = 100;
const MAIN_SIZE = 64;
const SUMMARY_BITS = 1918;
const SUMMARY_BYTES = 240;
const HASH_COUNT = 7;
const TARGET_FPR_PPM = 10000;
const SAMPLE_SIZES = [4, 10, 25, 50, 100];

type ResearchProduct = {
  productId: string;
  payload: string;
  digest: string;
  versionId: bigint;
  sourceBlockNumber: bigint;
  packedFilter: string;
  mainPositions: number[];
  summaryBits: number[];
};

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

function researchProduct(
  productId: string,
  revision: number,
  versionId: bigint,
  sourceBlockNumber: bigint,
): ResearchProduct {
  const normalizedId = productId.trim().toUpperCase();
  const payload = JSON.stringify({
    product_id: normalizedId,
    research_revision: revision,
  });
  const digest = ethers.keccak256(ethers.toUtf8Bytes(payload));
  const idToken = ethers.toUtf8Bytes(`product-id:${normalizedId}`);
  const digestToken = ethers.concat([
    ethers.toUtf8Bytes("record-digest:"),
    ethers.getBytes(digest),
  ]);
  const summaryBits = [
    ...new Set([
      ...hashPositions(idToken, SUMMARY_BITS, HASH_COUNT),
      ...hashPositions(ethers.getBytes(digestToken), SUMMARY_BITS, HASH_COUNT),
    ]),
  ].sort((left, right) => left - right);
  const packed = new Uint8Array(SUMMARY_BYTES);
  for (const bit of summaryBits) {
    packed[Math.floor(bit / 8)] |= 1 << (bit % 8);
  }

  return {
    productId: normalizedId,
    payload,
    digest,
    versionId,
    sourceBlockNumber,
    packedFilter: ethers.hexlify(Buffer.from(packed)),
    mainPositions: hashPositions(
      ethers.toUtf8Bytes(normalizedId),
      MAIN_SIZE,
      HASH_COUNT,
    ).sort((left, right) => left - right),
    summaryBits,
  };
}

function contributionId(productId: string): string {
  return ethers.keccak256(ethers.toUtf8Bytes(`c2:${productId}`));
}

function productKey(productId: string): string {
  return ethers.keccak256(ethers.toUtf8Bytes(productId));
}

async function receiptGas(
  transaction: ContractTransactionResponse,
): Promise<bigint> {
  const receipt = await transaction.wait();
  if (!receipt || receipt.status !== 1) {
    throw new Error("Research transaction failed");
  }
  return receipt.gasUsed;
}

async function publishFullGeneration(
  contract: BaseContract,
  publisher: Signer,
  products: ResearchProduct[],
): Promise<{ gasUsed: string; transactionCount: number }> {
  const revision = await contract.getFunction("stateRevision")();
  let gas = await receiptGas(
    await contract.connect(publisher).getFunction("beginIndexGeneration")(
      revision,
      SUMMARY_BITS,
      HASH_COUNT,
      TARGET_FPR_PPM,
      products.length,
      SUMMARY_BYTES,
    ),
  );
  let transactionCount = 1;
  const generationId = (await contract.getFunction("nextGenerationId")()) - 1n;
  const chunkSize = Number(await contract.getFunction("MAX_FILTERS_PER_CHUNK")());

  for (let start = 0; start < products.length; start += chunkSize) {
    const chunk = products.slice(start, start + chunkSize);
    gas += await receiptGas(
      await contract.connect(publisher).getFunction("uploadFilterChunk")(
        generationId,
        start,
        chunk.map((product) => product.versionId),
        chunk.map((product) => product.sourceBlockNumber),
        chunk.map((product) => product.packedFilter),
      ),
    );
    transactionCount++;
  }

  const summary = new Uint8Array(SUMMARY_BYTES);
  for (const product of products) {
    const filter = ethers.getBytes(product.packedFilter);
    for (let index = 0; index < summary.length; index++) {
      summary[index] |= filter[index];
    }
  }
  gas += await receiptGas(
    await contract.connect(publisher).getFunction("uploadSummaryChunk")(
      generationId,
      0,
      ethers.hexlify(summary),
    ),
  );
  transactionCount++;

  gas += await receiptGas(
    await contract.connect(publisher).getFunction("finalizeIndexGeneration")(generationId),
  );
  transactionCount++;

  expect(await contract.getFunction("isIndexFresh")()).to.equal(true);
  return { gasUsed: gas.toString(), transactionCount };
}

async function insertProduct(
  contract: BaseContract,
  writer: Signer,
  productId: string,
  operationId: string,
): Promise<ResearchProduct> {
  const base = researchProduct(productId, 1, 0n, 0n);
  await receiptGas(
    await contract.connect(writer).getFunction("insertProduct")(
      ethers.id(operationId),
      base.productId,
      base.payload,
      base.digest,
      0,
    ),
  );
  const versionId = await contract.getFunction("getLatestVersionId")(base.productId);
  const version = await contract.getFunction("getVersion")(versionId);
  return researchProduct(
    base.productId,
    1,
    versionId,
    version.sourceBlockNumber,
  );
}

async function deployBaseline() {
  const [admin, writer, publisher] = await ethers.getSigners();
  const factory = await ethers.getContractFactory("SupplyChainBaseline", admin);
  const contract = await factory.deploy();
  await contract.waitForDeployment();
  await contract.getFunction("grantRole")(
    await contract.getFunction("WRITER")(),
    await writer.getAddress(),
  );
  await contract.getFunction("grantRole")(
    await contract.getFunction("INDEX_PUBLISHER")(),
    await publisher.getAddress(),
  );
  return { contract, writer, publisher };
}

async function deployC2(writer: Signer, ledger: BaseContract) {
  const factory = await ethers.getContractFactory("C2IncrementalExperiment");
  const contract = await factory.deploy(
    await ledger.getAddress(),
    MAIN_SIZE,
    SUMMARY_BITS,
    CAPACITY,
    HASH_COUNT,
    HASH_COUNT,
    await writer.getAddress(),
  );
  await contract.waitForDeployment();
  return contract;
}

async function addC2Contribution(
  contract: BaseContract,
  ledger: BaseContract,
  writer: Signer,
  product: ResearchProduct,
  operationName: string,
): Promise<bigint> {
  return receiptGas(
    await contract.connect(writer).getFunction("addContribution")(
      ethers.id(`c2-operation:${operationName}`),
      contributionId(product.productId),
      product.productId,
      productKey(product.productId),
      product.versionId,
      product.sourceBlockNumber,
      product.digest,
      await contract.getFunction("stateRevision")(),
      await ledger.getFunction("stateRevision")(),
      product.mainPositions,
      product.summaryBits,
    ),
  );
}

async function synchronizeC2(
  contract: BaseContract,
  ledger: BaseContract,
  writer: Signer,
): Promise<bigint> {
  return receiptGas(
    await contract.connect(writer).getFunction("synchronizeProductLedger")(
      await contract.getFunction("stateRevision")(),
      await ledger.getFunction("stateRevision")(),
    ),
  );
}

describe("C2 research gas comparison", function () {
  it("compares fixed-capacity full rebuild publication with counter updates", async function () {
    expect(network.name).to.equal("hardhat");
    const measurements: Array<Record<string, unknown>> = [];

    for (const size of SAMPLE_SIZES) {
      const { contract: baseline, writer, publisher } = await deployBaseline();
      const c2 = await deployC2(writer, baseline);
      const products: ResearchProduct[] = [];

      for (let index = 0; index < size; index++) {
        products.push(
          await insertProduct(
            baseline,
            writer,
            `MED-${size}-${String(index).padStart(3, "0")}`,
            `research-insert-${size}-${index}`,
          ),
        );
      }

      const initialRebuild = await publishFullGeneration(
        baseline,
        publisher,
        products,
      );
      let initialC2Gas = 0n;
      for (const product of products) {
        initialC2Gas += await addC2Contribution(
          c2,
          baseline,
          writer,
          product,
          `initial-${size}-${product.productId}`,
        );
      }
      initialC2Gas += await synchronizeC2(c2, baseline, writer);
      expect(await c2.getFunction("activeCount")()).to.equal(BigInt(size));

      const updateTarget = products[0];
      const updatedPayload = researchProduct(
        updateTarget.productId,
        2,
        updateTarget.versionId,
        updateTarget.sourceBlockNumber,
      );
      await receiptGas(
        await baseline.connect(writer).getFunction("updateProduct")(
          ethers.id(`research-update-${size}`),
          updateTarget.productId,
          updateTarget.versionId,
          updatedPayload.payload,
          updatedPayload.digest,
        ),
      );
      const updatedVersionId = await baseline.getFunction("getLatestVersionId")(
        updateTarget.productId,
      );
      const updatedVersion = await baseline.getFunction("getVersion")(updatedVersionId);
      const updatedProduct = researchProduct(
        updateTarget.productId,
        2,
        updatedVersionId,
        updatedVersion.sourceBlockNumber,
      );
      products[0] = updatedProduct;

      const baselineUpdate = await publishFullGeneration(
        baseline,
        publisher,
        products,
      );
      const c2UpdateGas = await receiptGas(
        await c2.connect(writer).getFunction("replaceContribution")(
          ethers.id(`c2-operation:update:${size}`),
          contributionId(updatedProduct.productId),
          updatedProduct.productId,
          updatedProduct.versionId,
          updatedProduct.sourceBlockNumber,
          updatedProduct.digest,
          await c2.getFunction("stateRevision")(),
          await baseline.getFunction("stateRevision")(),
          updatedProduct.mainPositions,
          updatedProduct.summaryBits,
        ),
      );
      const c2UpdateSyncGas = await synchronizeC2(c2, baseline, writer);

      const deleted = products[1];
      await receiptGas(
        await baseline.connect(writer).getFunction("deleteProduct")(
          ethers.id(`research-delete-${size}`),
          deleted.productId,
          deleted.versionId,
        ),
      );
      products.splice(1, 1);
      const baselineDelete = await publishFullGeneration(
        baseline,
        publisher,
        products,
      );
      const c2DeleteGas = await receiptGas(
        await c2.connect(writer).getFunction("removeContribution")(
          ethers.id(`c2-operation:delete:${size}`),
          contributionId(deleted.productId),
          deleted.productId,
          await c2.getFunction("stateRevision")(),
          await baseline.getFunction("stateRevision")(),
        ),
      );
      const c2DeleteSyncGas = await synchronizeC2(c2, baseline, writer);

      const inserted = await insertProduct(
        baseline,
        writer,
        `MED-${size}-NEW`,
        `research-reinsert-${size}`,
      );
      products.push(inserted);
      const baselineInsert = await publishFullGeneration(
        baseline,
        publisher,
        products,
      );
      const c2InsertGas = await addC2Contribution(
        c2,
        baseline,
        writer,
        inserted,
        `insert-${size}`,
      );
      const c2InsertSyncGas = await synchronizeC2(c2, baseline, writer);

      expect(await c2.getFunction("activeCount")()).to.equal(BigInt(size));
      expect(await c2.getFunction("stateRevision")()).to.equal(BigInt(size + 7));
      expect(await c2.getFunction("isFresh")()).to.equal(true);
      measurements.push({
        active_products: size,
        fixed_capacity: CAPACITY,
        summary_bits: SUMMARY_BITS,
        initial: {
          baseline_full_rebuild_gas: initialRebuild.gasUsed,
          baseline_transaction_count: initialRebuild.transactionCount,
          c2_incremental_population_gas: initialC2Gas.toString(),
          c2_transaction_count: size,
        },
        operations: {
          update: {
            baseline_full_rebuild_gas: baselineUpdate.gasUsed,
            baseline_transaction_count: baselineUpdate.transactionCount,
            c2_counter_update_gas: (c2UpdateGas + c2UpdateSyncGas).toString(),
              c2_transaction_count: 2,
          },
          delete: {
            baseline_full_rebuild_gas: baselineDelete.gasUsed,
            baseline_transaction_count: baselineDelete.transactionCount,
            c2_counter_update_gas: (c2DeleteGas + c2DeleteSyncGas).toString(),
            c2_transaction_count: 2,
          },
          insert: {
            baseline_full_rebuild_gas: baselineInsert.gasUsed,
            baseline_transaction_count: baselineInsert.transactionCount,
            c2_counter_update_gas: (c2InsertGas + c2InsertSyncGas).toString(),
            c2_transaction_count: 2,
          },
        },
        comparison_scope: "index maintenance only; baseline product-ledger mutation gas excluded",
      });
    }

    const outputPath = process.env.C2_RESEARCH_GAS_OUTPUT;
    if (outputPath) {
      if (existsSync(outputPath)) {
        throw new Error(`Refusing to overwrite existing gas report: ${outputPath}`);
      }
      writeFileSync(
        outputPath,
        `${JSON.stringify(
          {
            network: network.name,
            fixed_capacity: CAPACITY,
            main_size: MAIN_SIZE,
            summary_bits: SUMMARY_BITS,
            hash_count: HASH_COUNT,
            target_fpr_ppm: TARGET_FPR_PPM,
            measurements,
          },
          null,
          2,
        )}\n`,
        { encoding: "utf-8", flag: "wx" },
      );
    }
  });
});
