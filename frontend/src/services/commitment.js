import { buildPoseidon } from "circomlibjs";

const ATTRIBUTE_NAMES = [
  "product_id",
  "product_name",
  "batch_number",
  "manufacturing_date",
  "expiry_date",
  "manufacturer_id",
  "shipment_id",
  "quantity",
  "source_location",
  "destination_location",
];

const STRING_ATTRIBUTE_INDEXES = [0, 1, 2, 5, 6, 8, 9];
const MAX_STRING_BYTES = 62;
const FIELD_MODULUS =
  21888242871839275222246405745257275088548364400416034343698204186575808495617n;

let poseidonInstance;

const getPoseidon = async () => {
  if (!poseidonInstance) {
    poseidonInstance = await buildPoseidon();
  }

  return poseidonInstance;
};

const hashToDecimal = (poseidon, inputs) => {
  return poseidon.F.toString(poseidon(inputs));
};

const encodeString = (value) => {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error("String attributes must not be empty.");
  }

  const bytes = new TextEncoder().encode(value);

  if (bytes.length > MAX_STRING_BYTES) {
    throw new Error("String attributes must not exceed 62 UTF-8 bytes.");
  }

  let packed0 = 0n;
  let packed1 = 0n;

  for (let i = 0; i < bytes.length; i++) {
    if (i < 31) {
      packed0 += BigInt(bytes[i]) * (256n ** BigInt(i));
    } else {
      packed1 += BigInt(bytes[i]) * (256n ** BigInt(i - 31));
    }
  }

  return {
    packed0: packed0.toString(),
    packed1: packed1.toString(),
    length: bytes.length,
  };
};

const validateSalt = (salt) => {
  if (!/^\d+$/.test(String(salt))) {
    throw new Error("Invalid attribute salt.");
  }

  const value = BigInt(salt);

  if (value < 0n || value >= 2n ** 248n) {
    throw new Error("Attribute salt must be a 248-bit value.");
  }

  return value;
};

const validateNumericValue = (value, attribute) => {
  if (!/^\d+$/.test(String(value))) {
    throw new Error(`${attribute} must contain a non-negative integer.`);
  }

  const number = BigInt(value);

  const maxBits = attribute === "quantity" ? 64n : 27n;

  if (number >= 2n ** maxBits) {
    throw new Error(`${attribute} exceeds the circuit's allowed range.`);
  }

  return number;
};

export const generateAttributeCommitments = async (attributes, salts) => {
  if (!attributes || !salts) {
    throw new Error("Attributes and salts are required.");
  }

  const poseidon = await getPoseidon();
  const commitments = [];

  for (let i = 0; i < ATTRIBUTE_NAMES.length; i++) {
    const attribute = ATTRIBUTE_NAMES[i];

    if (!(attribute in attributes) || !(attribute in salts)) {
      throw new Error(`Missing ${attribute} or its salt.`);
    }

    let attributeValue;

    if (STRING_ATTRIBUTE_INDEXES.includes(i)) {
      const encoded = encodeString(attributes[attribute]);

      attributeValue = hashToDecimal(poseidon, [
        BigInt(encoded.packed0),
        BigInt(encoded.packed1),
        BigInt(encoded.length),
      ]);
    } else {
      attributeValue = validateNumericValue(
        attributes[attribute],
        attribute
      ).toString();
    }

    const salt = validateSalt(salts[attribute]);

    commitments.push(
      hashToDecimal(poseidon, [
        BigInt(attributeValue),
        salt,
      ])
    );
  }

  return commitments;
};

export { ATTRIBUTE_NAMES };