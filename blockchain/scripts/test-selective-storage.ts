import { network } from "hardhat";
import { readFileSync } from "node:fs";

async function main() {
    const { ethers } = await network.connect();

    const [admin, manufacturer] = await ethers.getSigners();

    const contractAddress =
        "0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9";

    const input = JSON.parse(
        readFileSync(
            new URL("../circuits/build/selective/manufacturer_input.json", import.meta.url),
            "utf8"
        )
    );

    const commitments = input.commitments.map((value: string) =>
        BigInt(value)
    );

    if (commitments.length !== 10) {
        throw new Error("Expected exactly 10 commitments");
    }

    const contract = await ethers.getContractAt(
        "SelectiveZKPVerifier",
        contractAddress
    );

    console.log("Admin:", admin.address);
    console.log("Manufacturer:", manufacturer.address);

    const currentRole = await contract.stakeholderRoles(
        manufacturer.address
    );

    if (currentRole === 0n) {
        const registerTx = await contract
            .connect(admin)
            .registerStakeholder(manufacturer.address, 2);

        await registerTx.wait();
        console.log("Manufacturer registered.");
    } else {
        console.log("Manufacturer already registered.");
    }

    const storageTx = await contract
        .connect(manufacturer)
        .storeRecord(commitments);

    const receipt = await storageTx.wait();

    if (!receipt) {
        throw new Error("Storage transaction receipt not found");
    }

    let recordId: bigint | undefined;

    for (const log of receipt.logs) {
        try {
            const parsed = contract.interface.parseLog(log);

            if (parsed?.name === "RecordStored") {
                recordId = parsed.args.recordId;
                break;
            }
        } catch {
            // Ignore logs from other contracts.
        }
    }

    if (recordId === undefined) {
        throw new Error("RecordStored event not found");
    }

    const storedCommitments =
        await contract.getRecordCommitments(recordId);

    const matches = storedCommitments.every(
        (value: bigint, index: number) => value === commitments[index]
    );

    console.log("Storage transaction hash:", receipt.hash);
    console.log("Record ID:", recordId.toString());
    console.log("Stored commitment count:", storedCommitments.length);
    console.log("Commitments match:", matches);

    if (!matches) {
        throw new Error("On-chain commitment mismatch");
    }

    console.log("On-chain storage test passed.");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
