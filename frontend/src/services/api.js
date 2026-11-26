
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
