import { expect } from "chai";
import { ethers } from "hardhat";

async function deploy(capacity = 4) {
  const [admin, writer, other] = await ethers.getSigners();
  const ledgerFactory = await ethers.getContractFactory("SupplyChainBaseline", admin);
  const ledger = await ledgerFactory.deploy();
  await ledger.waitForDeployment();
  await ledger.getFunction("grantRole")(
    await ledger.getFunction("WRITER")(),
    writer.address,
  );

  const c2Factory = await ethers.getContractFactory("C2IncrementalExperiment", admin);
  const c2 = await c2Factory.deploy(
    await ledger.getAddress(),
    4,
    16,
    capacity,
    3,
    3,
    writer.address,
  );
  await c2.waitForDeployment();
  return { ledger, c2, writer, other };
}

function contributionId(productId: string): string {
  return ethers.keccak256(ethers.toUtf8Bytes(`c2:${productId}`));
}

function productKey(productId: string): string {
  return ethers.keccak256(ethers.toUtf8Bytes(productId));
}

async function insertProduct(ledger: any, writer: any, productId: string, revision = 1) {
  const payload = JSON.stringify({ product_id: productId, revision });
  const digest = ethers.keccak256(ethers.toUtf8Bytes(payload));
  await ledger.connect(writer).getFunction("insertProduct")(
    ethers.id(`insert:${productId}:${revision}`),
    productId,
    payload,
    digest,
    0,
  );
  const [, version] = await ledger.getFunction("getCurrentProduct")(productId);
  return { productId, version, digest };
}

async function addContribution(c2: any, ledger: any, writer: any, product: any, name: string) {
  await c2.connect(writer).getFunction("addContribution")(
    ethers.id(`operation:${name}`),
    contributionId(product.productId),
    product.productId,
    productKey(product.productId),
    product.version.versionId,
    product.version.sourceBlockNumber,
    product.digest,
    await c2.getFunction("stateRevision")(),
    await ledger.getFunction("stateRevision")(),
    [0, 1],
    [2, 5],
  );
}

async function synchronize(c2: any, ledger: any, writer: any) {
  await c2.connect(writer).getFunction("synchronizeProductLedger")(
    await c2.getFunction("stateRevision")(),
    await ledger.getFunction("stateRevision")(),
  );
}

describe("C2IncrementalExperiment", function () {
  it("adds and removes authoritative contributions and reports freshness", async function () {
    const { ledger, c2, writer } = await deploy();
    const product = await insertProduct(ledger, writer, "C2-PRODUCT-1");

    await addContribution(c2, ledger, writer, product, "add-1");
    await synchronize(c2, ledger, writer);

    expect(await c2.getFunction("activeCount")()).to.equal(1);
    expect(await c2.getFunction("getMainCount")(0)).to.equal(1);
    expect(await c2.getFunction("getSummaryCount")(0, 2)).to.equal(1);
    expect(await c2.getFunction("isFresh")()).to.equal(true);

    await ledger.connect(writer).getFunction("deleteProduct")(
      ethers.id("delete:product-1"),
      product.productId,
      product.version.versionId,
    );
    await c2.connect(writer).getFunction("removeContribution")(
      ethers.id("operation:remove-1"),
      contributionId(product.productId),
      product.productId,
      await c2.getFunction("stateRevision")(),
      await ledger.getFunction("stateRevision")(),
    );
    expect(await c2.getFunction("isFresh")()).to.equal(false);
    await synchronize(c2, ledger, writer);

    expect(await c2.getFunction("activeCount")()).to.equal(0);
    expect(await c2.getFunction("getMainCount")(0)).to.equal(0);
    expect(await c2.getFunction("getSummaryCount")(0, 2)).to.equal(0);
    expect(await c2.getFunction("contributionByProduct")(productKey(product.productId)))
      .to.equal(ethers.ZeroHash);
    expect(await c2.getFunction("isFresh")()).to.equal(true);
  });

  it("preserves shared counters when one authoritative product is removed", async function () {
    const { ledger, c2, writer } = await deploy();
    const first = await insertProduct(ledger, writer, "C2-PRODUCT-1");
    const second = await insertProduct(ledger, writer, "C2-PRODUCT-2");

    await addContribution(c2, ledger, writer, first, "add-first");
    await addContribution(c2, ledger, writer, second, "add-second");
    await synchronize(c2, ledger, writer);

    await ledger.connect(writer).getFunction("deleteProduct")(
      ethers.id("delete:first"),
      first.productId,
      first.version.versionId,
    );
    await c2.connect(writer).getFunction("removeContribution")(
      ethers.id("operation:remove-first"),
      contributionId(first.productId),
      first.productId,
      await c2.getFunction("stateRevision")(),
      await ledger.getFunction("stateRevision")(),
    );
    await synchronize(c2, ledger, writer);

    expect(await c2.getFunction("getMainCount")(0)).to.equal(1);
    expect(await c2.getFunction("getSummaryCount")(0, 2)).to.equal(1);
    expect(await c2.getFunction("activeCount")()).to.equal(1);
  });

  it("replaces a contribution using the current authoritative version and digest", async function () {
    const { ledger, c2, writer } = await deploy();
    const product = await insertProduct(ledger, writer, "C2-PRODUCT-1");
    await addContribution(c2, ledger, writer, product, "add-for-replace");
    await synchronize(c2, ledger, writer);

    const updatedPayload = JSON.stringify({ product_id: product.productId, revision: 2 });
    const updatedDigest = ethers.keccak256(ethers.toUtf8Bytes(updatedPayload));
    await ledger.connect(writer).getFunction("updateProduct")(
      ethers.id("update:product-1"),
      product.productId,
      product.version.versionId,
      updatedPayload,
      updatedDigest,
    );
    const [, version] = await ledger.getFunction("getCurrentProduct")(product.productId);
    await c2.connect(writer).getFunction("replaceContribution")(
      ethers.id("operation:replace-1"),
      contributionId(product.productId),
      product.productId,
      version.versionId,
      version.sourceBlockNumber,
      updatedDigest,
      await c2.getFunction("stateRevision")(),
      await ledger.getFunction("stateRevision")(),
      [1],
      [4, 7],
    );

    const updated = await c2.getFunction("getContribution")(contributionId(product.productId));
    expect(updated.active).to.equal(true);
    expect(updated.productKey).to.equal(productKey(product.productId));
    expect(updated.versionId).to.equal(version.versionId);
    expect(updated.payloadDigest).to.equal(updatedDigest);
    expect(updated.selectedMainPositions).to.deep.equal([1n]);
    expect(updated.setSummaryBits).to.deep.equal([4n, 7n]);
    expect(await c2.getFunction("getMainCount")(0)).to.equal(0);
    expect(await c2.getFunction("getMainCount")(1)).to.equal(1);
    expect(await c2.getFunction("getSummaryCount")(1, 4)).to.equal(1);
    await synchronize(c2, ledger, writer);
    expect(await c2.getFunction("isFresh")()).to.equal(true);
  });

  it("rejects malformed, duplicate, stale, and replayed operations", async function () {
    const { ledger, c2, writer, other } = await deploy(1);
    const product = await insertProduct(ledger, writer, "C2-PRODUCT-1");
    const calls = [
      [ethers.id("invalid-main-duplicate"), [0, 0], [2]],
      [ethers.id("invalid-summary-duplicate"), [0], [2, 2]],
      [ethers.id("invalid-main-range"), [4], [2]],
      [ethers.id("invalid-summary-range"), [0], [16]],
    ];

    for (const [operationId, main, summary] of calls) {
      await expect(
        c2.connect(writer).getFunction("addContribution")(
          operationId,
          contributionId(product.productId),
          product.productId,
          productKey(product.productId),
          product.version.versionId,
          product.version.sourceBlockNumber,
          product.digest,
          0,
          await ledger.getFunction("stateRevision")(),
          main,
          summary,
        ),
      ).to.be.reverted;
      expect(await c2.getFunction("activeCount")()).to.equal(0);
      expect(await c2.getFunction("stateRevision")()).to.equal(0);
    }

    const replayId = ethers.id("operation:once");
    await c2.connect(writer).getFunction("addContribution")(
      replayId,
      contributionId(product.productId),
      product.productId,
      productKey(product.productId),
      product.version.versionId,
      product.version.sourceBlockNumber,
      product.digest,
      0,
      await ledger.getFunction("stateRevision")(),
      [0],
      [2],
    );
    await expect(
      c2.connect(other).getFunction("synchronizeProductLedger")(
        1,
        await ledger.getFunction("stateRevision")(),
      ),
    ).to.be.revertedWith("Unauthorized writer");

    const second = await insertProduct(ledger, writer, "C2-PRODUCT-2");
    await expect(
      c2.connect(writer).getFunction("addContribution")(
        replayId,
        contributionId(second.productId),
        second.productId,
        productKey(second.productId),
        second.version.versionId,
        second.version.sourceBlockNumber,
        second.digest,
        1,
        await ledger.getFunction("stateRevision")(),
        [1],
        [3],
      ),
    ).to.be.revertedWith("Operation already used");
    await expect(
      c2.connect(writer).getFunction("addContribution")(
        ethers.id("stale-index"),
        contributionId(second.productId),
        second.productId,
        productKey(second.productId),
        second.version.versionId,
        second.version.sourceBlockNumber,
        second.digest,
        0,
        await ledger.getFunction("stateRevision")(),
        [1],
        [3],
      ),
    ).to.be.revertedWith("Index revision mismatch");
    await expect(
      c2.connect(writer).getFunction("addContribution")(
        ethers.id("stale-ledger"),
        contributionId(second.productId),
        second.productId,
        productKey(second.productId),
        second.version.versionId,
        second.version.sourceBlockNumber,
        second.digest,
        1,
        1,
        [1],
        [3],
      ),
    ).to.be.revertedWith("Product ledger revision mismatch");
    expect(await c2.getFunction("stateRevision")()).to.equal(1);
  });

  it("rejects a product version or digest not equal to the ledger head", async function () {
    const { ledger, c2, writer } = await deploy();
    const product = await insertProduct(ledger, writer, "C2-PRODUCT-1");
    await expect(
      c2.connect(writer).getFunction("addContribution")(
        ethers.id("wrong-digest"),
        contributionId(product.productId),
        product.productId,
        productKey(product.productId),
        product.version.versionId,
        product.version.sourceBlockNumber,
        ethers.id("not-the-ledger-digest"),
        0,
        await ledger.getFunction("stateRevision")(),
        [0],
        [2],
      ),
    ).to.be.revertedWith("Payload digest mismatch");
  });
});
