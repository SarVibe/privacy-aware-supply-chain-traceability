import { network } from "hardhat";
import { readFileSync } from "node:fs";

async function main() {
    const { ethers } = await network.connect();
    const [admin, , , warehouse] = await ethers.getSigners();

    const contract = await ethers.getContractAt(
        "SelectiveZKPVerifier",
        "0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9"
    );

    const proof = JSON.parse(readFileSync(
        new URL("../circuits/build/selective/warehouse_record1_proof.json", import.meta.url),
        "utf8"
    ));

    const signals = JSON.parse(readFileSync(
        new URL("../circuits/build/selective/warehouse_record1_public.json", import.meta.url),
        "utf8"
    ));

    const recordId = 1;
    const stored = await contract.getRecordCommitments(recordId);

    if (signals.length !== 11 || BigInt(signals[10]) !== 4n) {
        throw new Error("Invalid Warehouse public signals");
    }

    if (!stored.every((v: bigint, i: number) => v === BigInt(signals[i]))) {
        throw new Error("On-chain commitments do not match");
    }

    const role = await contract.stakeholderRoles(warehouse.address);

    if (role === 0n) {
        const registration = await contract.connect(admin)
            .registerStakeholder(warehouse.address, 4);
        await registration.wait();
    } else if (role !== 4n) {
        throw new Error("Wallet already has a different role");
    }

    const pA = proof.pi_a.slice(0, 2).map((v: string) => BigInt(v));
    const pB = [
        [BigInt(proof.pi_b[0][1]), BigInt(proof.pi_b[0][0])],
        [BigInt(proof.pi_b[1][1]), BigInt(proof.pi_b[1][0])]
    ];
    const pC = proof.pi_c.slice(0, 2).map((v: string) => BigInt(v));

    const tx = await contract.connect(warehouse)
        .verifySupplyChain(recordId, pA, pB, pC);

    const receipt = await tx.wait();

    console.log("Warehouse wallet:", warehouse.address);
    console.log("Verification transaction:", receipt?.hash);
    console.log("Gas used:", receipt?.gasUsed.toString());
    console.log("Warehouse on-chain verification passed.");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
