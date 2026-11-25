// Export an encrypted salt package as a JSON file.
export const exportSaltPackage = (encryptedPackage, transactionId) => {
  if (!encryptedPackage || !transactionId) {
    throw new Error("Encrypted package and transaction ID are required.");
  }

  if (encryptedPackage.format !== "C3-ZKP-ENCRYPTED-SALTS-V1") {
    throw new Error("Invalid encrypted salt package.");
  }

  const fileContent = JSON.stringify(encryptedPackage, null, 2);
  const blob = new Blob([fileContent], {
    type: "application/json",
  });

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = `encrypted-salts-${transactionId}.json`;

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  URL.revokeObjectURL(url);
};

// Import an encrypted salt package from a JSON file.
export const importSaltPackage = async (file) => {
  if (!file || file.type !== "application/json") {
    throw new Error("Please select a valid JSON package.");
  }

  const content = await file.text();
  const encryptedPackage = JSON.parse(content);

  if (
    encryptedPackage?.format !== "C3-ZKP-ENCRYPTED-SALTS-V1" ||
    !encryptedPackage?.encryptedData
  ) {
    throw new Error("Invalid encrypted salt package.");
  }

  return encryptedPackage;
};
