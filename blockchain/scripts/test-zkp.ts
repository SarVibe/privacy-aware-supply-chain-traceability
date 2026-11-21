
import { network } from "hardhat";

async function main() {
    const { ethers } = await network.connect();

    const [admin, manufacturer, logistics, pharmacy] =
        await ethers.getSigners();

    const zkpAddress =
        "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";

    const zkp = await ethers.getContractAt(
        "ZKPVerifier",
        zkpAddress
    );

    console.log("Starting stakeholder tests...\n");

    
    async function registerIfNeeded(
        contract: any,
        address: string,
        role: number
    ) {
        const currentRole = await contract.stakeholderRoles(address);

        if (currentRole === 0n) {
            await (
                await contract.registerStakeholder(address, role)
            ).wait();
        }
    }
    // 1. Register stakeholders only if not already registered
    await registerIfNeeded(zkp, manufacturer.address, 2);
    await registerIfNeeded(zkp, logistics.address, 3);
    await registerIfNeeded(zkp, pharmacy.address, 6);

    console.log(
        "Manufacturer role:",
        (await zkp.stakeholderRoles(manufacturer.address)).toString()
    );

    console.log(
        "Logistics role:",
        (await zkp.stakeholderRoles(logistics.address)).toString()
    );

    console.log(
        "Pharmacy role:",
        (await zkp.stakeholderRoles(pharmacy.address)).toString()
    );
    // 4. Admin must not access attributes
    console.log(
        "\nAdmin product_id access:",
        await zkp.canAccessAttribute(1, 0)
    );

    // 5. Logistics allowed attribute: product_id (0)
    console.log(
        "Logistics product_id access:",
        await zkp.canAccessAttribute(3, 0)
    );

    // 6. Logistics denied attribute: product_name (1)
    console.log(
        "Logistics product_name access:",
        await zkp.canAccessAttribute(3, 1)
    );

    // 7. Pharmacy allowed attribute: expiry_date (4)
    console.log(
        "Pharmacy expiry_date access:",
        await zkp.canAccessAttribute(6, 4)
    );

    // 8. Pharmacy denied attribute: shipment_id (6)
    console.log(
        "Pharmacy shipment_id access:",
        await zkp.canAccessAttribute(6, 6)
    );

    // 9. Revoke Logistics Provider
    await (
        await zkp.revokeStakeholder(logistics.address)
    ).wait();

    console.log(
        "\nLogistics role after revocation:",
        (await zkp.stakeholderRoles(logistics.address)).toString()
    );

    // 10. Verify revoked stakeholder cannot access verification
    try {
        await zkp.connect(logistics).verifySupplyChain.staticCall(
            [0, 0],
            [[0, 0], [0, 0]],
            [0, 0],
            Array(11).fill(0),
            [0]
        );

        console.log("ERROR: Revoked stakeholder was not rejected.");
    } catch {
        console.log("Revoked stakeholder verification: Rejected");
    }

    console.log("\nStakeholder tests completed.");
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
