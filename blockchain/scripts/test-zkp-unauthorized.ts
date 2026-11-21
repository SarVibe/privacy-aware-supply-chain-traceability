
import { network } from "hardhat";
import { readFileSync } from "fs";

async function main() {
    const { ethers } = await network.connect();

    const [admin, , logistics] = await ethers.getSigners();

    const zkpAddress =
        "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";

    const zkp = await ethers.getContractAt(
        "ZKPVerifier",
        zkpAddress
    );

    // Register Logistics Provider if not already registered
    const currentRole = await zkp.stakeholderRoles(logistics.address);

    if (currentRole === 0n) {
        const tx = await zkp.connect(admin)
            .registerStakeholder(logistics.address, 3);

        await tx.wait();
    }

    console.log(
        "Logistics role:",
        (await zkp.stakeholderRoles(logistics.address)).toString()
    );

    // Load a valid Groth16 proof
    const proof = JSON.parse(
        readFileSync("./proof.json", "utf8")
    );

    const publicSignals = JSON.parse(
        readFileSync("./public.json", "utf8")
    );

    // Convert proof into Solidity tuple format
    const pA: [string, string] = [
        proof.pi_a[0],
        proof.pi_a[1]
    ];

    const pB: [[string, string], [string, string]] = [
        [proof.pi_b[0][1], proof.pi_b[0][0]],
        [proof.pi_b[1][1], proof.pi_b[1][0]]
    ];

    const pC: [string, string] = [
        proof.pi_c[0],
        proof.pi_c[1]
    ];

    // Logistics Provider requests product_name (index 1)
    const requestedAttributes = [1];

    console.log("Starting unauthorized access test...\n");
    console.log("Logistics Provider:", logistics.address);
    console.log("Requested attribute: product_name (index 1)");

    try {
        await zkp.connect(logistics)
            .verifySupplyChain.staticCall(
                pA,
                pB,
                pC,
                publicSignals,
                requestedAttributes
            );

        console.log("ERROR: Unauthorized access was accepted!");

    } catch (error: any) {
        console.log("Unauthorized attribute request rejected.");
        console.log("Reason:", error.shortMessage || error.message);
    }

    console.log("\nUnauthorized access test completed.");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
