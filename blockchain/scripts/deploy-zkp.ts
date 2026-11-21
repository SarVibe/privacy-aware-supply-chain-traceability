
import { network } from "hardhat";

async function main() {
    const { ethers } = await network.connect();

    // Get the deployer account
    const [deployer] = await ethers.getSigners();

    console.log("Deploying contracts...");
    console.log("Admin address:", deployer.address);

    // Deploy Groth16 verifier
    const Groth16Verifier = await ethers.getContractFactory(
        "Groth16Verifier"
    );

    const groth16Verifier = await Groth16Verifier.deploy();
    await groth16Verifier.waitForDeployment();

    const groth16Address = await groth16Verifier.getAddress();

    console.log("Groth16Verifier deployed:", groth16Address);

    // Deploy main ZKP verifier
    const ZKPVerifier = await ethers.getContractFactory(
        "ZKPVerifier"
    );

    const zkpVerifier = await ZKPVerifier.deploy(groth16Address);
    await zkpVerifier.waitForDeployment();

    const zkpAddress = await zkpVerifier.getAddress();

    console.log("ZKPVerifier deployed:", zkpAddress);

    // Confirm deployer is Admin
    const adminRole = await zkpVerifier.stakeholderRoles(
        deployer.address
    );

    console.log("Admin role:", adminRole.toString());
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
