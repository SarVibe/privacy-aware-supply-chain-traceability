import { ethers } from "ethers";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import dotenv from "dotenv";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "../..");
dotenv.config({ path: path.join(projectRoot, ".env") });

async function main() {
  console.log(
    "Starting deployment of HarmonizedSupplyChain contract (Hardhat 3 / ESM)...",
  );

  const rpcUrl = process.env.BLOCKCHAIN_RPC_URL || "http://127.0.0.1:8545";
  const privateKey = process.env.BLOCKCHAIN_PRIVATE_KEY;
  if (!privateKey) {
    throw new Error(
      "BLOCKCHAIN_PRIVATE_KEY is required. Set it in the project-root .env file.",
    );
  }

  const provider = new ethers.JsonRpcProvider(rpcUrl);

  // Check if RPC node is accessible
  try {
    const network = await provider.getNetwork();
    console.log(`Connected to Network: Chain ID ${network.chainId}`);
  } catch (error) {
    console.error(`\n[ERROR] Unable to connect to RPC node at ${rpcUrl}`);
    console.error(
      "Please ensure your Hardhat node is running in another terminal via: 'npx hardhat node'",
    );
    process.exit(1);
  }

  const wallet = new ethers.Wallet(privateKey, provider);
  console.log("Deploying contract with account:", wallet.address);

  const balance = await provider.getBalance(wallet.address);
  console.log("Account balance:", ethers.formatEther(balance), "ETH");

  // Load contract artifact
  const artifactPath = path.resolve(
    __dirname,
    "../artifacts/contracts/HarmonizedSupplyChain.sol/HarmonizedSupplyChain.json",
  );

  if (!fs.existsSync(artifactPath)) {
    throw new Error(
      `Artifact not found at ${artifactPath}. Please run 'npx hardhat compile' first.`,
    );
  }

  const artifact = JSON.parse(fs.readFileSync(artifactPath, "utf-8"));
  const factory = new ethers.ContractFactory(
    artifact.abi,
    artifact.bytecode,
    wallet,
  );

  console.log("Submitting deployment transaction...");
  const bloomFilterBits = Number(process.env.DEFAULT_BF_LENGTH || 1024);
  if (!Number.isInteger(bloomFilterBits) || bloomFilterBits <= 0 || bloomFilterBits % 8 !== 0) {
    throw new Error("DEFAULT_BF_LENGTH must be a positive multiple of 8.");
  }
  const bloomFilterBytes = bloomFilterBits / 8;
  const contract = await factory.deploy(bloomFilterBytes);
  await contract.waitForDeployment();

  const contractAddress = await contract.getAddress();
  console.log("\n==================================================");
  console.log("HarmonizedSupplyChain deployed successfully!");
  console.log("Contract Address:", contractAddress);
  console.log("==================================================\n");

  // Update CONTRACT_ADDRESS in .env file safely
  const envPath = path.join(projectRoot, ".env");
  let envContent = fs.existsSync(envPath)
    ? fs.readFileSync(envPath, "utf-8")
    : "";
  if (/(^|\r?\n)CONTRACT_ADDRESS=/.test(envContent)) {
    envContent = envContent.replace(
      /(^|\r?\n)CONTRACT_ADDRESS=[^\r\n]*/,
      `$1CONTRACT_ADDRESS=${contractAddress}`,
    );
  } else {
    envContent = `${envContent.trimEnd()}\nCONTRACT_ADDRESS=${contractAddress}\n`;
  }
  fs.writeFileSync(envPath, envContent, "utf-8");
  console.log("Updated project-root CONTRACT_ADDRESS successfully.");
}

main().catch((error) => {
  console.error("Deployment failed:", error);
  process.exitCode = 1;
});
