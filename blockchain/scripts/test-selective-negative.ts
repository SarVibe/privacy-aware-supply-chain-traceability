import { network } from "hardhat";
import { readFileSync } from "node:fs";

async function main() {
    const { ethers } = await network.connect();
    const [admin] = await ethers.getSigners();

    const contract = await ethers.getContractAt(
        "SelectiveZKPVerifier",
        "0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9"
    );

    const proof = JSON.parse(readFileSync(
        new URL("../circuits/build/selective/pharmacy_record1_proof.json", import.meta.url),
        "utf8"
    ));

    const pA = proof.pi_a.slice(0, 2).map((v: string) => BigInt(v));
    const pB = [
        [BigInt(proof.pi_b[0][1]), BigInt(proof.pi_b[0][0])],
        [BigInt(proof.pi_b[1][1]), BigInt(proof.pi_b[1][0])]
    ];
    const pC = proof.pi_c.slice(0, 2).map((v: string) => BigInt(v));

    try {
        await contract.connect(admin)
            .verifySupplyChain.staticCall(1, pA, pB, pC);

        throw new Error("TEST FAILED: Admin verification was allowed");
    } catch (error: any) {
        if (contract.interface.parseError(error.data)?.args[0] !== "Admin cannot verify records") {
            throw error;
        }

        console.log("PASS: Admin verification rejected");
    }
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});

