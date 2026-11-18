import { ethers } from "hardhat";
import fs from "fs";
import path from "path";

async function main() {
    const [deployer] = await ethers.getSigners();

    console.log("Deploying with account:", deployer.address);

    const Factory = await ethers.getContractFactory(
        "SupplyChainBaseline"
    );

    const contract = await Factory.deploy();

    await contract.waitForDeployment();

    const address = await contract.getAddress();
    const deploymentTx = contract.deploymentTransaction();

    if (!deploymentTx) {
        throw new Error("Deployment transaction not found");
    }

    const receipt = await deploymentTx.wait();

    if (!receipt) {
        throw new Error("Deployment receipt not found");
    }

    const network = await ethers.provider.getNetwork();

    const artifactPath = path.join(
        __dirname,
        "../artifacts/contracts/SupplyChainBaseline.sol/SupplyChainBaseline.json"
    );

    const artifact = JSON.parse(
        fs.readFileSync(artifactPath, "utf-8")
    );

    const deploymentInfo = {
        contractName: "SupplyChainBaseline",
        address,
        chainId: Number(network.chainId),
        deploymentTransactionHash: receipt.hash,
        deploymentBlockNumber: receipt.blockNumber,
        abi: artifact.abi,
    };

    const deploymentDirectory = path.join(__dirname, "../deployments");

    fs.mkdirSync(deploymentDirectory, { recursive: true });

    fs.writeFileSync(
        path.join(deploymentDirectory, "localhost.json"),
        JSON.stringify(deploymentInfo, null, 2)
    );

    console.log("Contract deployed successfully!");
    console.log("Contract address:", address);
    console.log("Chain ID:", Number(network.chainId));
    console.log("Deployment block:", receipt.blockNumber);
    console.log("Transaction hash:", receipt.hash);
    console.log("Deployment info saved to deployments/localhost.json");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});