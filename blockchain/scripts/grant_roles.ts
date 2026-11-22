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

  for (const name of ["WRITER", "INDEX_PUBLISHER"]) {
    const role = await ledger[name]();
    if (await ledger.hasRole(role, wallet)) {
      console.log(`${wallet} already has ${name}`);
      continue;
    }
    await (await ledger.grantRole(role, wallet)).wait();
    console.log(`${name} granted to ${wallet}`);
  }
}

main().catch((e) => { console.error(e); process.exitCode = 1; });