import { network } from "hardhat";

async function main() {
    const { ethers } = await network.connect();

    const [deployer] = await ethers.getSigners();

    console.log("Deploying Selective ZKP contracts...");
    console.log("Admin address:", deployer.address);

    const SelectiveGroth16Verifier = await ethers.getContractFactory(
        "SelectiveGroth16Verifier"
    );

    const groth16Verifier = await SelectiveGroth16Verifier.deploy();
    await groth16Verifier.waitForDeployment();

    const groth16Address = await groth16Verifier.getAddress();

    console.log("SelectiveGroth16Verifier deployed:", groth16Address);

    const SelectiveZKPVerifier = await ethers.getContractFactory(
        "SelectiveZKPVerifier"
    );

    const zkpVerifier = await SelectiveZKPVerifier.deploy(groth16Address);
    await zkpVerifier.waitForDeployment();

    const zkpAddress = await zkpVerifier.getAddress();

    console.log("SelectiveZKPVerifier deployed:", zkpAddress);

    const adminRole = await zkpVerifier.stakeholderRoles(deployer.address);

    console.log("Admin role:", adminRole.toString());
    console.log("Deployment completed.");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
