import { network } from "hardhat";
import { readFileSync } from "node:fs";

async function main() {
    const { ethers } = await network.connect();
    const [, manufacturer] = await ethers.getSigners();

    const contractAddress = "0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9";
    const recordId = 1;

    const proof = JSON.parse(
        readFileSync(
            new URL("../circuits/build/selective/manufacturer_proof.json", import.meta.url),
            "utf8"
        )
    );

    const publicSignals = JSON.parse(
        readFileSync(
            new URL("../circuits/build/selective/manufacturer_public.json", import.meta.url),
            "utf8"
        )
    );

    const contract = await ethers.getContractAt(
        "SelectiveZKPVerifier",
        contractAddress
    );

    const storedCommitments = await contract.getRecordCommitments(recordId);

    const commitmentsMatch = storedCommitments.every(
        (value: bigint, index: number) =>
            value === BigInt(publicSignals[index])
    );

    if (!commitmentsMatch) {
        throw new Error("Proof commitments do not match on-chain record");
    }

    if (BigInt(publicSignals[10]) !== 2n) {
        throw new Error("Proof role is not Manufacturer");
    }

    const role = await contract.stakeholderRoles(manufacturer.address);

    if (role !== 2n) {
        throw new Error("Connected wallet is not registered as Manufacturer");
    }

    const pA = proof.pi_a.slice(0, 2).map((value: string) => BigInt(value));

    const pB = [
        [BigInt(proof.pi_b[0][1]), BigInt(proof.pi_b[0][0])],
        [BigInt(proof.pi_b[1][1]), BigInt(proof.pi_b[1][0])]
    ];

    const pC = proof.pi_c.slice(0, 2).map((value: string) => BigInt(value));

    console.log("Manufacturer:", manufacturer.address);
    console.log("Record ID:", recordId);
    console.log("On-chain commitments match:", commitmentsMatch);
    console.log("Proof role:", publicSignals[10]);
    console.log("Submitting proof for on-chain verification...");

    const tx = await contract
        .connect(manufacturer)
        .verifySupplyChain(recordId, pA, pB, pC);

    const receipt = await tx.wait();

    if (!receipt) {
        throw new Error("Verification transaction receipt not found");
    }

    console.log("Verification transaction:", receipt.hash);
    console.log("Gas used:", receipt.gasUsed.toString());

    for (const log of receipt.logs) {
        try {
            const parsed = contract.interface.parseLog(log);

            if (parsed?.name === "VerificationCompleted") {
                console.log("Verification event:", parsed.name);
                console.log("Verified record ID:", parsed.args.recordId.toString());
                console.log("Stakeholder:", parsed.args.stakeholder);
                console.log("Role:", parsed.args.role.toString());
                console.log("Attribute mask:", parsed.args.attributeMask.toString());
            }
        } catch {
            // Ignore unrelated logs.
        }
    }

    console.log("On-chain ZKP verification test passed.");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
