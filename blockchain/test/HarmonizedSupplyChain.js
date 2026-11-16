import { expect } from "chai";
import hre from "hardhat";

const { ethers } = hre;

describe("HarmonizedSupplyChain", function () {
  async function deployFixture() {
    const [owner, submitter, attacker] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("HarmonizedSupplyChain");
    const contract = await Factory.deploy(16);
    await contract.waitForDeployment();
    return { contract, owner, submitter, attacker };
  }

  it("authorizes the deployer and rejects unauthorized writers", async function () {
    const { contract, attacker } = await deployFixture();
    const filter = ethers.hexlify(ethers.randomBytes(16));
    const hash = ethers.keccak256("0x01");

    await expect(
      contract.connect(attacker).storeHarmonizedRecord("R1", "C1", filter, hash),
    ).to.be.revertedWith("Caller is not an authorized submitter");
  });

  it("validates Bloom-filter length, record IDs, and duplicate hashes", async function () {
    const { contract } = await deployFixture();
    const validFilter = ethers.hexlify(ethers.randomBytes(16));
    const invalidFilter = ethers.hexlify(ethers.randomBytes(15));
    const hash = ethers.keccak256("0x01");

    await expect(
      contract.storeHarmonizedRecord("R1", "C1", invalidFilter, hash),
    ).to.be.revertedWith("Invalid Bloom filter length");

    await contract.storeHarmonizedRecord("R1", "C1", validFilter, hash);

    await expect(
      contract.storeHarmonizedRecord("R1", "C2", validFilter, ethers.keccak256("0x02")),
    ).to.be.revertedWith("Record ID already committed");

    await expect(
      contract.storeHarmonizedRecord("R2", "C2", validFilter, hash),
    ).to.be.revertedWith("Record hash already committed");
  });

  it("allows the owner to authorize submitters and pause writes", async function () {
    const { contract, owner, submitter } = await deployFixture();
    const filter = ethers.hexlify(ethers.randomBytes(16));

    await contract.connect(owner).setSubmitter(submitter.address, true);
    await contract.connect(submitter).storeHarmonizedRecord(
      "R1",
      "C1",
      filter,
      ethers.keccak256("0x01"),
    );

    await contract.connect(owner).setPaused(true);
    await expect(
      contract.storeHarmonizedRecord("R2", "C1", filter, ethers.keccak256("0x02")),
    ).to.be.revertedWith("Contract is paused");
  });
});
