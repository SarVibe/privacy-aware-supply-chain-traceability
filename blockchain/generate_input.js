
import { buildPoseidon } from "circomlibjs";
import fs from "node:fs";

const poseidon = await buildPoseidon();

const STRING_ATTRIBUTES = [
    "product_id",
    "product_name",
    "batch_number",
    "manufacturer_id",
    "shipment_id",
    "source_location",
    "destination_location"
];

const NUMERIC_ATTRIBUTES = [
    "manufacturing_date",
    "expiry_date",
    "quantity"
];

// Encode actual and expected string values
function encodeString(actualValue, expectedValue) {
    const actualBytes = Array.from(
        Buffer.from(String(actualValue), "utf8")
    );

    const expectedBytes = Array.from(
        Buffer.from(String(expectedValue), "utf8")
    );

    if (actualBytes.length > 62 || expectedBytes.length > 62) {
        throw new Error("String exceeds 62 UTF-8 bytes");
    }

    const actualPadded = new Array(62).fill(0);
    const expectedPadded = new Array(62).fill(0);

    actualBytes.forEach((byte, i) => {
        actualPadded[i] = byte;
    });

    expectedBytes.forEach((byte, i) => {
        expectedPadded[i] = byte;
    });

    function pack(bytes, start) {
        let packed = 0n;

        for (let i = 0; i < 31; i++) {
            packed += BigInt(bytes[start + i]) * (256n ** BigInt(i));
        }

        return packed;
    }

    const actualPacked0 = pack(actualPadded, 0);
    const actualPacked1 = pack(actualPadded, 31);

    const expectedPacked0 = pack(expectedPadded, 0);
    const expectedPacked1 = pack(expectedPadded, 31);

    const expectedHash = poseidon([
        expectedPacked0,
        expectedPacked1,
        BigInt(expectedBytes.length)
    ]);

    return {
        bytes: actualPadded.map(String),
        length: String(actualBytes.length),
        expectedHash: poseidon.F.toString(expectedHash)
    };
}

// Validate and encode date or quantity values
function validateNumeric(value, attribute) {
    const number = BigInt(value);

    if (number < 0n) {
        throw new Error(`${attribute} cannot be negative`);
    }

    if (attribute === "quantity" && number > (2n ** 64n - 1n)) {
        throw new Error("Quantity exceeds uint64 range");
    }

    if (
        attribute !== "quantity" &&
        number > (2n ** 27n - 1n)
    ) {
        throw new Error(`${attribute} exceeds 27-bit range`);
    }

    return number.toString();
}

// Read input and output file paths
const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
    throw new Error(
        "Usage: node generate_input.js <source.json> <output.json>"
    );
}

const source = JSON.parse(
    fs.readFileSync(inputPath, "utf8")
);

if (!source.actual || !source.expected) {
    throw new Error("Both actual and expected objects are required");
}

const input = {};

// Process seven string attributes
for (const attribute of STRING_ATTRIBUTES) {
    if (
        source.actual[attribute] === undefined ||
        source.expected[attribute] === undefined
    ) {
        throw new Error(`Missing attribute: ${attribute}`);
    }

    const encoded = encodeString(
        source.actual[attribute],
        source.expected[attribute]
    );

    input[`${attribute}_bytes`] = encoded.bytes;
    input[`${attribute}_length`] = encoded.length;
    input[`${attribute}_expectedHash`] = encoded.expectedHash;
}

// Process two dates and quantity
for (const attribute of NUMERIC_ATTRIBUTES) {
    if (
        source.actual[attribute] === undefined ||
        source.expected[attribute] === undefined
    ) {
        throw new Error(`Missing attribute: ${attribute}`);
    }

    input[attribute] = validateNumeric(
        source.actual[attribute],
        attribute
    );

    input[`${attribute}_expected`] = validateNumeric(
        source.expected[attribute],
        attribute
    );
}

// Save generated Circom input
fs.writeFileSync(outputPath, JSON.stringify(input, null, 2));

console.log("ZKP input generated successfully!");
console.log("String attributes:", STRING_ATTRIBUTES.length);
console.log("Total attributes:", 10);
