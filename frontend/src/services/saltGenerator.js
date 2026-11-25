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

// Generate a secure, BN254-compatible salt for each attribute.
export const generateAttributeSalts = (attributes = ATTRIBUTE_NAMES) => {
  if (!globalThis.crypto?.getRandomValues) {
    throw new Error("Secure random number generation is unavailable.");
  }

  const salts = {};

  for (const attribute of attributes) {
    // 31 bytes (248 bits) always fit within the BN254 scalar field.
    const randomBytes = new Uint8Array(31);
    globalThis.crypto.getRandomValues(randomBytes);

    const saltHex = Array.from(randomBytes)
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");

    // Convert hexadecimal salt into a decimal string for Circom.
    salts[attribute] = BigInt(`0x${saltHex}`).toString(10);
  }

  return salts;
};