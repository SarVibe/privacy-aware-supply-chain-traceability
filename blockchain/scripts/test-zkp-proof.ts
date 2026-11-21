
import { network } from "hardhat";
import { readFileSync } from "fs";

async function main() {
    const { ethers } = await network.connect();

    const [admin, manufacturer] = await ethers.getSigners();

    const zkpAddress =
        "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";

    const zkp = await ethers.getContractAt(
        "ZKPVerifier",
        zkpAddress
    );

    // Load generated proof and public signals
    const proof = JSON.parse(
        readFileSync("./proof.json", "utf8")
    );

    const publicSignals = JSON.parse(
        readFileSync("./public.json", "utf8")
    );


    // Convert snarkjs proof into fixed-size Solidity tuples
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

    // Request all 10 attributes
    const requestedAttributes: number[] = [
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9
    ];


    console.log("Starting on-chain ZKP verification...\n");

    console.log("Manufacturer:", manufacturer.address);
    console.log("Public isValid:", publicSignals[0]);

    // Simulate verification first
    const result = await zkp.connect(manufacturer)
        .verifySupplyChain.staticCall(
            pA,
            pB,
            pC,
            publicSignals,
            requestedAttributes
        );

    console.log("\nOn-chain verification result:", result);

    // Submit actual blockchain transaction
    const tx = await zkp.connect(manufacturer)
        .verifySupplyChain(
            pA,
            pB,
            pC,
            publicSignals,
            requestedAttributes
        );

    const receipt = await tx.wait();

    console.log("Transaction hash:", receipt?.hash);
    console.log("Gas used:", receipt?.gasUsed.toString());
    console.log("\nZKP verification completed!");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
