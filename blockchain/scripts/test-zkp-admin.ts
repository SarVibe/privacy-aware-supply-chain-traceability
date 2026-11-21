
import { network } from "hardhat";

async function main() {
    const { ethers } = await network.connect();

    const [admin] = await ethers.getSigners();

    const zkpAddress =
        "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";

    const zkp = await ethers.getContractAt(
        "ZKPVerifier",
        zkpAddress
    );

    console.log("Starting Admin restriction test...\n");

    console.log("Admin address:", admin.address);

    console.log(
        "Admin role:",
        (await zkp.stakeholderRoles(admin.address)).toString()
    );

    try {
        await zkp.connect(admin).verifySupplyChain.staticCall(
            [0, 0],
            [[0, 0], [0, 0]],
            [0, 0],
            Array(11).fill(0),
            [0]
        );

        console.log("ERROR: Admin verification was accepted!");

    } catch (error: any) {
        console.log("Admin verification rejected.");
        console.log("Reason:", error.shortMessage || error.message);
    }

    console.log("\nAdmin restriction test completed.");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
