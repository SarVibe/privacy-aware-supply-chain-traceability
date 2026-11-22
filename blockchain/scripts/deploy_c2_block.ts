import { ethers } from "hardhat";
import { loadEnvFile } from "node:process";
import path from "node:path";

loadEnvFile(
  path.resolve(__dirname, "../../backend/.env")
);

function positiveInteger(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive safe integer`);
  }
  return value;
}

async function main() {
  const ledgerAddress = process.env.C2_PRODUCT_LEDGER_ADDRESS;
  if (!ledgerAddress) throw new Error("C2_PRODUCT_LEDGER_ADDRESS is required");

  const [deployer] = await ethers.getSigners();
  const writerAddress = process.env.C2_WRITER_ADDRESS ?? deployer.address;
  const factory = await ethers.getContractFactory("C2BlockIncrementalExperiment", deployer);
  const contract = await factory.deploy(
    ledgerAddress,
    positiveInteger("C2_MAIN_SIZE", 64),
    positiveInteger("C2_SUMMARY_SIZE", 192),      // must equal BlockC2Manager.summary_size
    positiveInteger("C2_BLOCK_CAPACITY", 100),
    positiveInteger("C2_MAX_PRODUCTS_PER_BLOCK", 10),
    writerAddress,
  );
  await contract.waitForDeployment();

  console.log(`C2_BLOCK_EXPERIMENT_ADDRESS=${await contract.getAddress()}`);
  console.log(`C2_PRODUCT_LEDGER_ADDRESS=${ledgerAddress}`);
  console.log(`C2_WRITER_ADDRESS=${writerAddress}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});