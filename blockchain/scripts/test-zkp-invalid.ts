
import { network } from "hardhat";
import { readFileSync } from "fs";

async function main() {
    const { ethers } = await network.connect();

    const [, manufacturer] = await ethers.getSigners();

    const zkpAddress =
        "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";

    const zkp = await ethers.getContractAt(
        "ZKPVerifier",
        zkpAddress
    );

    // Load invalid proof and public signals
    const proof = JSON.parse(
        readFileSync("./proof_invalid.json", "utf8")
    );

    const publicSignals = JSON.parse(
        readFileSync("./public_invalid.json", "utf8")
    );


    // Convert proof into fixed-size Solidity tuples
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

    const requestedAttributes: number[] = [
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9
    ];


    console.log("Starting invalid ZKP test...\n");
    console.log("Manufacturer:", manufacturer.address);
    console.log("Public isValid:", publicSignals[0]);

    try {
        await zkp.connect(manufacturer)
            .verifySupplyChain.staticCall(
                pA,
                pB,
                pC,
                publicSignals,
                requestedAttributes
            );

        console.log("ERROR: Invalid proof was accepted!");

    } catch (error: any) {
        console.log("Invalid proof rejected by smart contract.");
        console.log("Reason:", error.shortMessage || error.message);
    }

    console.log("\nInvalid ZKP test completed.");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
