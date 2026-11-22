
import axiosInstance from "./axios";

// Health check
export const checkBackendHealth = () => {
  return axiosInstance.get("/health");
};

// Generate ZKP proof
export const generateZKPProof = (data) => {
  return axiosInstance.post("/zkp/generate-proof", data);
};

// Verify ZKP on blockchain
export const verifyZKPOnChain = (data) => {
  return axiosInstance.post("/zkp/verify-on-chain", data);
};

// Register stakeholder (Admin)
export const registerStakeholder = (data) => {
  return axiosInstance.post("/admin/register-stakeholder", data);
};

// Revoke stakeholder (Admin)
export const revokeStakeholder = (data) => {
  return axiosInstance.post("/admin/revoke-stakeholder", data);
};
