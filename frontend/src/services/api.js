
import axiosInstance from "./axios";

// Health check
export const checkBackendHealth = () => {
  return axiosInstance.get("/health");
};

// Retrieve a record using its original storage transaction hash
export const getRecordByTransactionHash = (transactionHash) => {
  return axiosInstance.get(`/records/${encodeURIComponent(transactionHash)}`);
};

// Generate a selective ZKP proof
export const generateZKPProof = (data) => {
  return axiosInstance.post("/zkp/generate-proof", data);
};

// Register stakeholder (Admin)
export const registerStakeholder = (data) => {
  return axiosInstance.post("/admin/register-stakeholder", data);
};

// Revoke stakeholder (Admin)
export const revokeStakeholder = (data) => {
  return axiosInstance.post("/admin/revoke-stakeholder", data);
};

// Retrieve logged-in stakeholder verification history
export const getVerificationHistory = () => {
  return axiosInstance.get("/history/verifications");
};

// Retrieve records stored by the logged-in manufacturer
export const getManufacturerStorageHistory = () => {
  return axiosInstance.get("/history/storage");
};

// Retrieve stakeholder verifications for the manufacturer's records
export const getManufacturerVerificationHistory = () => {
  return axiosInstance.get("/history/manufacturer-verifications");
};

