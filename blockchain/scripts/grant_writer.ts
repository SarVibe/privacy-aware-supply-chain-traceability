import { ethers } from "hardhat";
import fs from "fs";
import path from "path";

async function main() {
  const [admin] = await ethers.getSigners();

  const deployment = JSON.parse(
    fs.readFileSync(path.join(__dirname, "../deployments/localhost.json"), "utf-8")
  );
  const ledger = await ethers.getContractAt("SupplyChainBaseline", deployment.address, admin);

  const wallet = process.env.WALLET_ADDRESS ?? admin.address;
  const WRITER = await ledger.WRITER();

  if (await ledger.hasRole(WRITER, wallet)) {
    console.log(`${wallet} already has WRITER`);
    return;
  }
  await (await ledger.grantRole(WRITER, wallet)).wait();
  console.log(`WRITER granted to ${wallet}`);
}

main().catch((e) => { console.error(e); process.exitCode = 1; });