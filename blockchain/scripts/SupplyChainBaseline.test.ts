
import { expect } from "chai";
import { ethers } from "hardhat";
import { SupplyChainBaseline__factory } from "../typechain-types";

describe("SupplyChainBaseline", function () {
  async function deployFixture() {
    const [admin, writer, publisher] = await ethers.getSigners();

   const Factory = new SupplyChainBaseline__factory(admin);

const contract = await Factory.deploy();
await contract.waitForDeployment();

    const WRITER = await contract.WRITER();
    const INDEX_PUBLISHER = await contract.INDEX_PUBLISHER();

    await contract.grantRole(WRITER, writer.address);
    await contract.grantRole(INDEX_PUBLISHER, publisher.address);

    return { contract, admin, writer, publisher };
  }

  it("should allow an authorized writer to insert a product", async function () {
    const { contract, writer } = await deployFixture();

    const productId = "PROD-001";
    const payload = JSON.stringify({
      productId: "PROD-001",
      name: "Organic Rice",
      origin: "Jaffna",
      quantity: 100
    });

    const digest = ethers.keccak256(
      ethers.toUtf8Bytes(payload)
    );

    const operationId = ethers.id("operation-insert-001");

    await contract.connect(writer).insertProduct(
      operationId,
      productId,
      payload,
      digest,
      0
    );

    expect(await contract.getLatestVersionId(productId)).to.equal(1);
    expect(await contract.isProductActive(productId)).to.equal(true);
    expect(await contract.stateRevision()).to.equal(1);
    expect(await contract.activeProductCount()).to.equal(1);
  });

  it("should preserve product history after an update", async function () {
    const { contract, writer } = await deployFixture();

    const productId = "PROD-002";

    const payload1 = JSON.stringify({
      productId: "PROD-002",
      quantity: 100
    });

    const digest1 = ethers.keccak256(
      ethers.toUtf8Bytes(payload1)
    );

    await contract.connect(writer).insertProduct(
      ethers.id("operation-insert-002"),
      productId,
      payload1,
      digest1,
      0
    );

    const payload2 = JSON.stringify({
      productId: "PROD-002",
      quantity: 150
    });

    const digest2 = ethers.keccak256(
      ethers.toUtf8Bytes(payload2)
    );

    await contract.connect(writer).updateProduct(
      ethers.id("operation-update-002"),
      productId,
      1,
      payload2,
      digest2
    );

    expect(await contract.getLatestVersionId(productId)).to.equal(2);
    expect(await contract.stateRevision()).to.equal(2);

    const history = await contract.getProductHistory(
      productId,
      0,
      10
    );

    expect(history.length).to.equal(2);
    expect(history[0]).to.equal(1);
    expect(history[1]).to.equal(2);

    const current = await contract.getCurrentProduct(productId);

    expect(current.active).to.equal(true);
    expect(current.version.versionNumber).to.equal(2);
    expect(current.version.previousVersionId).to.equal(1);
  });

  
  it("should create a tombstone when deleting a product", async function () {
    const { contract, writer } = await deployFixture();

    const productId = "PROD-003";
    const payload = JSON.stringify({
      productId: "PROD-003",
      quantity: 50
    });

    const digest = ethers.keccak256(
      ethers.toUtf8Bytes(payload)
    );

    await contract.connect(writer).insertProduct(
      ethers.id("operation-insert-003"),
      productId,
      payload,
      digest,
      0
    );

    await contract.connect(writer).deleteProduct(
      ethers.id("operation-delete-003"),
      productId,
      1
    );

    expect(await contract.isProductActive(productId)).to.equal(false);
    expect(await contract.getLatestVersionId(productId)).to.equal(2);
    expect(await contract.activeProductCount()).to.equal(0);
    expect(await contract.stateRevision()).to.equal(2);

    const deleted = await contract.getVersion(2);

    expect(deleted.operation).to.equal(2);
    expect(deleted.canonicalPayload).to.equal("");
  });

  it("should allow reinsertion after deletion", async function () {
    const { contract, writer } = await deployFixture();

    const productId = "PROD-004";

    const payload1 = JSON.stringify({
      productId: "PROD-004",
      quantity: 20
    });

    const digest1 = ethers.keccak256(
      ethers.toUtf8Bytes(payload1)
    );

    await contract.connect(writer).insertProduct(
      ethers.id("operation-insert-004"),
      productId,
      payload1,
      digest1,
      0
    );

    await contract.connect(writer).deleteProduct(
      ethers.id("operation-delete-004"),
      productId,
      1
    );

    const payload2 = JSON.stringify({
      productId: "PROD-004",
      quantity: 30
    });

    const digest2 = ethers.keccak256(
      ethers.toUtf8Bytes(payload2)
    );

    await contract.connect(writer).insertProduct(
      ethers.id("operation-reinsert-004"),
      productId,
      payload2,
      digest2,
      2
    );

    expect(await contract.isProductActive(productId)).to.equal(true);
    expect(await contract.getLatestVersionId(productId)).to.equal(3);
    expect(await contract.activeProductCount()).to.equal(1);
    expect(await contract.stateRevision()).to.equal(3);

    const history = await contract.getProductHistory(
      productId,
      0,
      10
    );

    expect(history.length).to.equal(3);
  });

  
  it("should reject product insertion from an unauthorized account", async function () {
    const { contract, admin } = await deployFixture();

    const productId = "PROD-005";
    const payload = JSON.stringify({
      productId: "PROD-005",
      quantity: 10
    });

    const digest = ethers.keccak256(
      ethers.toUtf8Bytes(payload)
    );

    await expect(
      contract.connect(admin).insertProduct(
        ethers.id("operation-unauthorized-005"),
        productId,
        payload,
        digest,
        0
      )
    ).to.be.revertedWith("Unauthorized role");
  });

  it("should reject reuse of an operation ID", async function () {
    const { contract, writer } = await deployFixture();

    const operationId = ethers.id("operation-duplicate-006");

    const payload1 = JSON.stringify({
      productId: "PROD-006",
      quantity: 10
    });

    const digest1 = ethers.keccak256(
      ethers.toUtf8Bytes(payload1)
    );

    await contract.connect(writer).insertProduct(
      operationId,
      "PROD-006",
      payload1,
      digest1,
      0
    );

    const payload2 = JSON.stringify({
      productId: "PROD-007",
      quantity: 20
    });

    const digest2 = ethers.keccak256(
      ethers.toUtf8Bytes(payload2)
    );

    await expect(
      contract.connect(writer).insertProduct(
        operationId,
        "PROD-007",
        payload2,
        digest2,
        0
      )
    ).to.be.revertedWith("Operation already used");
  });

  it("should reject an update with an incorrect expected version", async function () {
    const { contract, writer } = await deployFixture();

    const productId = "PROD-008";

    const payload = JSON.stringify({
      productId: "PROD-008",
      quantity: 10
    });

    const digest = ethers.keccak256(
      ethers.toUtf8Bytes(payload)
    );

    await contract.connect(writer).insertProduct(
      ethers.id("operation-insert-008"),
      productId,
      payload,
      digest,
      0
    );

    const updatedPayload = JSON.stringify({
      productId: "PROD-008",
      quantity: 20
    });

    const updatedDigest = ethers.keccak256(
      ethers.toUtf8Bytes(updatedPayload)
    );

    await expect(
      contract.connect(writer).updateProduct(
        ethers.id("operation-update-008"),
        productId,
        0,
        updatedPayload,
        updatedDigest
      )
    ).to.be.revertedWith("Expected version conflict");
  });

  
  it("should publish a complete Bloom index generation", async function () {
    const { contract, writer, publisher } = await deployFixture();

    const productId = "PROD-009";

    const payload = JSON.stringify({
      productId: "PROD-009",
      quantity: 100
    });

    const digest = ethers.keccak256(
      ethers.toUtf8Bytes(payload)
    );

    await contract.connect(writer).insertProduct(
      ethers.id("operation-insert-009"),
      productId,
      payload,
      digest,
      0
    );

    const mBits = 8;
    const hashCount = 2;
    const targetFprPpm = 10000;
    const filterBytes = "0x01";

    const generationTx = await contract
      .connect(publisher)
      .beginIndexGeneration(
        1,
        mBits,
        hashCount,
        targetFprPpm,
        1,
        1
      );

    await generationTx.wait();

    const generationId = await contract.nextGenerationId() - 1n;

    const version = await contract.getVersion(1);

    await contract.connect(publisher).uploadFilterChunk(
      generationId,
      0,
      [1],
      [version.sourceBlockNumber],
      [filterBytes]
    );

    await contract.connect(publisher).uploadSummaryChunk(
      generationId,
      0,
      filterBytes
    );

    await contract.connect(publisher).finalizeIndexGeneration(
      generationId
    );

    expect(await contract.activeGenerationId()).to.equal(generationId);
    expect(await contract.publishedIndexRevision()).to.equal(1);
    expect(await contract.isIndexFresh()).to.equal(true);

    const storedFilter = await contract.getGenerationFilter(
      generationId,
      0
    );

    expect(storedFilter.versionId).to.equal(1);
    expect(storedFilter.packedBits).to.equal(filterBytes);

    const storedSummary = await contract.getGenerationSummary(
      generationId
    );

    expect(storedSummary).to.equal(filterBytes);
  });

  
  it("should mark the published index as stale after a product update", async function () {
    const { contract, writer, publisher } = await deployFixture();

    const productId = "PROD-010";

    const payload1 = JSON.stringify({
      productId: "PROD-010",
      quantity: 100
    });

    const digest1 = ethers.keccak256(
      ethers.toUtf8Bytes(payload1)
    );

    await contract.connect(writer).insertProduct(
      ethers.id("operation-insert-010"),
      productId,
      payload1,
      digest1,
      0
    );

    const generationTx = await contract
      .connect(publisher)
      .beginIndexGeneration(1, 8, 2, 10000, 1, 1);

    await generationTx.wait();

    const generationId = (await contract.nextGenerationId()) - 1n;
    const version = await contract.getVersion(1);

    await contract.connect(publisher).uploadFilterChunk(
      generationId,
      0,
      [1],
      [version.sourceBlockNumber],
      ["0x01"]
    );

    await contract.connect(publisher).uploadSummaryChunk(
      generationId,
      0,
      "0x01"
    );

    await contract.connect(publisher).finalizeIndexGeneration(
      generationId
    );

    expect(await contract.isIndexFresh()).to.equal(true);

    const payload2 = JSON.stringify({
      productId: "PROD-010",
      quantity: 150
    });

    const digest2 = ethers.keccak256(
      ethers.toUtf8Bytes(payload2)
    );

    await contract.connect(writer).updateProduct(
      ethers.id("operation-update-010"),
      productId,
      1,
      payload2,
      digest2
    );

    expect(await contract.isIndexFresh()).to.equal(false);

    const status = await contract.getIndexStatus();

    expect(status.stale).to.equal(true);
    expect(status.currentRevision).to.equal(2);
    expect(status.indexRevision).to.equal(1);
  });

  it("should reject finalization of an incomplete generation", async function () {
    const { contract, writer, publisher } = await deployFixture();

    const productId = "PROD-011";

    const payload = JSON.stringify({
      productId: "PROD-011",
      quantity: 50
    });

    const digest = ethers.keccak256(
      ethers.toUtf8Bytes(payload)
    );

    await contract.connect(writer).insertProduct(
      ethers.id("operation-insert-011"),
      productId,
      payload,
      digest,
      0
    );

    await contract.connect(publisher).beginIndexGeneration(
      1,
      8,
      2,
      10000,
      1,
      1
    );

    const generationId = (await contract.nextGenerationId()) - 1n;

    await expect(
      contract.connect(publisher).finalizeIndexGeneration(
        generationId
      )
    ).to.be.revertedWith("Incomplete filter upload");
  });



});
