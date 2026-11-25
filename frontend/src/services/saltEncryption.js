
import { encryptSafely } from "@metamask/eth-sig-util";
import { getAddress } from "ethers";

const ENCRYPTION_VERSION = "x25519-xsalsa20-poly1305";
const PACKAGE_FORMAT = "C3-ZKP-ENCRYPTED-SALTS-V1";

const ALLOWED_ATTRIBUTES = [
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

// Request the stakeholder's encryption public key from MetaMask.
export const getWalletEncryptionPublicKey = async (walletAddress) => {
  if (!window.ethereum) {
    throw new Error("MetaMask is not installed.");
  }

  if (!walletAddress) {
    throw new Error("Wallet address is required.");
  }

  const address = getAddress(walletAddress);

  return await window.ethereum.request({
    method: "eth_getEncryptionPublicKey",
    params: [address],
  });
};

// Encrypt only the selected attribute salts for the intended stakeholder.
export const encryptSalts = async (
  publicKey,
  transactionId,
  recipientAddress,
  salts
) => {
  if (!publicKey || !transactionId || !recipientAddress) {
    throw new Error("Public key, transaction ID and recipient are required.");
  }

  if (!salts || typeof salts !== "object" || Array.isArray(salts)) {
    throw new Error("Valid attribute salts are required.");
  }

  const recipient = getAddress(recipientAddress);
  const attributes = Object.keys(salts);

  if (attributes.length === 0) {
    throw new Error("At least one attribute salt is required.");
  }

  for (const attribute of attributes) {
    if (!ALLOWED_ATTRIBUTES.includes(attribute)) {
      throw new Error(`Unsupported attribute: ${attribute}`);
    }

    if (!/^[0-9]+$/.test(salts[attribute])) {
      throw new Error(`Invalid decimal salt for ${attribute}.`);
    }

    if (BigInt(salts[attribute]) >= (1n << 248n)) {
      throw new Error(`Salt is outside the supported range: ${attribute}`);
    }
  }

  const payload = {
    format: PACKAGE_FORMAT,
    transactionId,
    recipientAddress: recipient,
    attributes,
    salts,
  };

  const encryptedData = await encryptSafely({
    publicKey,
    data: payload,
    version: ENCRYPTION_VERSION,
  });

  return {
    format: PACKAGE_FORMAT,
    encryptedData,
  };
};

// Decrypt and validate the package against the expected transaction and wallet.
export const decryptSalts = async (
  encryptedPackage,
  walletAddress,
  expectedTransactionId
) => {
  if (!window.ethereum) {
    throw new Error("MetaMask is not installed.");
  }

  if (
    encryptedPackage?.format !== PACKAGE_FORMAT ||
    !encryptedPackage?.encryptedData ||
    !walletAddress ||
    !expectedTransactionId
  ) {
    throw new Error("Invalid encrypted package or missing verification details.");
  }

  const recipient = getAddress(walletAddress);

  const decryptedData = await window.ethereum.request({
    method: "eth_decrypt",
    params: [
      JSON.stringify(encryptedPackage.encryptedData),
      recipient,
    ],
  });

  const payload = JSON.parse(decryptedData);

  if (
    payload?.format !== PACKAGE_FORMAT ||
    payload.transactionId !== expectedTransactionId ||
    getAddress(payload.recipientAddress) !== recipient
  ) {
    throw new Error("Salt package does not match this transaction or wallet.");
  }

  if (
    !Array.isArray(payload.attributes) ||
    !payload.salts ||
    typeof payload.salts !== "object" ||
    Array.isArray(payload.salts)
  ) {
    throw new Error("Invalid decrypted salt data.");
  }

  const saltKeys = Object.keys(payload.salts);

  if (
    payload.attributes.length === 0 ||
    new Set(payload.attributes).size !== payload.attributes.length ||
    payload.attributes.length !== saltKeys.length ||
    !payload.attributes.every(
      (attribute) =>
        ALLOWED_ATTRIBUTES.includes(attribute) &&
        saltKeys.includes(attribute) &&
        /^[0-9]+$/.test(payload.salts[attribute]) &&
        BigInt(payload.salts[attribute]) < (1n << 248n)
    )
  ) {
    throw new Error("Decrypted attribute salts failed validation.");
  }

  return {
    transactionId: payload.transactionId,
    recipientAddress: recipient,
    attributes: payload.attributes,
    salts: payload.salts,
  };
};
