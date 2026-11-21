
import { network } from "hardhat";

async function main() {
    const { ethers } = await network.connect();

    const [, , , , unregistered] = await ethers.getSigners();

    const zkpAddress =
        "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";

    const zkp = await ethers.getContractAt(
        "ZKPVerifier",
        zkpAddress
    );

    console.log("Starting unregistered stakeholder test...\n");

    console.log("Unregistered wallet:", unregistered.address);

    console.log(
        "Current role:",
        (await zkp.stakeholderRoles(unregistered.address)).toString()
    );

    try {
        await zkp.connect(unregistered).verifySupplyChain.staticCall(
            [0, 0],
            [[0, 0], [0, 0]],
            [0, 0],
            Array(11).fill(0),
            [0]
        );

        console.log("ERROR: Unregistered wallet was accepted!");

    } catch (error: any) {
        console.log("Unregistered stakeholder rejected.");
        console.log("Reason:", error.shortMessage || error.message);
    }

    console.log("\nUnregistered stakeholder test completed.");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
