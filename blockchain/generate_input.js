
import { buildPoseidon } from "circomlibjs";
import fs from "node:fs";

const poseidon = await buildPoseidon();


function encodeString(value) {
    const bytes = Array.from(Buffer.from(value, "utf8"));

    if (bytes.length > 62) {
        throw new Error(`String exceeds 62 UTF-8 bytes: ${value}`);
    }

    // Always create exactly 62 bytes.
    const paddedBytes = new Array(62).fill(0);

    for (let i = 0; i < bytes.length; i++) {
        paddedBytes[i] = bytes[i];
    }

    let packed0 = 0n;
    let packed1 = 0n;

    for (let i = 0; i < 31; i++) {
        packed0 += BigInt(paddedBytes[i]) * (256n ** BigInt(i));
    }

    for (let i = 31; i < 62; i++) {
        packed1 += BigInt(paddedBytes[i]) * (256n ** BigInt(i - 31));
    }

    const hash = poseidon([packed0, packed1, BigInt(bytes.length)]);

    return {
        bytes: paddedBytes.map(String),
        length: String(bytes.length),
        expectedHash: poseidon.F.toString(hash)
    };
}


const input = {};

const stringAttributes = {
    product_id: "PROD-1001",
    product_name: "Test Product",
    batch_number: "BATCH-001",
    manufacturer_id: "MFG-001",
    shipment_id: "SHIP-001",
    source_location: "Colombo",
    destination_location: "Jaffna"
};

for (const [attribute, value] of Object.entries(stringAttributes)) {
    const encoded = encodeString(value);

    input[`${attribute}_bytes`] = encoded.bytes;
    input[`${attribute}_length`] = encoded.length;
    input[`${attribute}_expectedHash`] = encoded.expectedHash;
}

// Exact-match test values
input.manufacturing_date = "20261101";
input.manufacturing_date_expected = "20261101";

input.expiry_date = "20271101";
input.expiry_date_expected = "20271101";

input.quantity = "100";
input.quantity_expected = "100";

fs.writeFileSync("input.json", JSON.stringify(input, null, 2));

console.log("input.json generated successfully!");
console.log("String attributes encoded:", Object.keys(stringAttributes).length);
console.log("Total attributes: 10");
