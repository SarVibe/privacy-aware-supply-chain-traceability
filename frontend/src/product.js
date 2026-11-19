import { keccak256, toUtf8Bytes } from "ethers";
import { poseidon7 } from "poseidon-lite";

export const DOSAGE_FORMS = ["Tablet", "Syrup", "Capsule", "Cream", "Injection"];

export function textToField(value, label) {
  const bytes = new TextEncoder().encode(value.trim());
  if (bytes.length === 0 || bytes.length > 31) {
    throw new Error(`${label} must contain between 1 and 31 UTF-8 bytes.`);
  }
  return BigInt(`0x${Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")}`);
}

export function priceToCents(value) {
  if (!/^\d{1,15}(\.\d{1,2})?$/.test(value)) {
    throw new Error("Price must be a non-negative amount with up to 2 decimal places.");
  }
  const [whole, fraction = ""] = value.split(".");
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  if (cents >= 1n << 64n) {
    throw new Error("Price is too large.");
  }
  return cents;
}

export function dateToUnixSeconds(value, label) {
  const parsed = new Date(`${value}T00:00:00.000Z`);
  const seconds = Math.floor(parsed.getTime() / 1000);
  if (!Number.isFinite(seconds) || seconds < 0 || seconds >= 2 ** 32) {
    throw new Error(`${label} is invalid or out of range.`);
  }
  return BigInt(seconds);
}

export function productCircuitInput(product) {
  const manufacturingDate = dateToUnixSeconds(product.manufacturingDate, "Manufacturing date");
  const expiryDate = dateToUnixSeconds(product.expiryDate, "Expiry date");
  if (expiryDate <= manufacturingDate) {
    throw new Error("Expiry date must be later than manufacturing date.");
  }
  return {
    productName: textToField(product.productName, "Product name").toString(),
    manufacturerName: textToField(product.manufacturerName, "Manufacturer name").toString(),
    dosageForm: DOSAGE_FORMS.indexOf(product.dosageForm).toString(),
    manufacturingDate: manufacturingDate.toString(),
    expiryDate: expiryDate.toString(),
    priceCents: priceToCents(product.price).toString(),
    salt: "0"
  };
}

export function productQgramHashes(product) {
  const fields = [
    product.productName,
    product.manufacturerName,
    product.dosageForm,
    product.manufacturingDate,
    product.expiryDate,
    priceToCents(product.price).toString()
  ];
  const normalized = fields.map((value) => value.trim().toLowerCase()).join("|");
  const characters = Array.from(normalized);
  const qgrams = new Set();
  for (let index = 0; index <= characters.length - 3; index += 1) {
    qgrams.add(keccak256(toUtf8Bytes(characters.slice(index, index + 3).join(""))));
  }
  return [...qgrams].sort();
}

export function createDiceSimilarity(firstHashes) {
  const first = new Set(firstHashes.map((hash) => hash.toLowerCase()));
  return (secondHashes) => {
    const second = new Set(secondHashes.map((hash) => hash.toLowerCase()));
    if (first.size === 0 && second.size === 0) return 1;
    if (first.size === 0 || second.size === 0) return 0;
    let intersection = 0;
    for (const hash of first) {
      if (second.has(hash)) intersection += 1;
    }
    return (2 * intersection) / (first.size + second.size);
  };
}

export function diceSimilarity(firstHashes, secondHashes) {
  return createDiceSimilarity(firstHashes)(secondHashes);
}

export async function calculateCommitment(circuitInput) {
  const values = [
    circuitInput.productName,
    circuitInput.manufacturerName,
    circuitInput.dosageForm,
    circuitInput.manufacturingDate,
    circuitInput.expiryDate,
    circuitInput.priceCents,
    circuitInput.salt
  ].map((value) => BigInt(value));
  return poseidon7(values).toString();
}

export function formatPrice(cents) {
  const value = BigInt(cents);
  return `${value / 100n}.${(value % 100n).toString().padStart(2, "0")}`;
}
