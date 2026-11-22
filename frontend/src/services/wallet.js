
import { BrowserProvider, Contract, getAddress } from "ethers";

const CONTRACT_ADDRESS = import.meta.env.VITE_ZKP_VERIFIER_ADDRESS;
const REQUIRED_CHAIN_ID = Number(import.meta.env.VITE_CHAIN_ID);

const ROLE_NAMES = {
  1: "Admin",
  2: "Manufacturer",
  3: "Logistics Provider",
  4: "Warehouse",
  5: "Distributor",
  6: "Pharmacy",
};

// Public smart contract ABI - role retrieval only
const CONTRACT_ABI = [
  "function stakeholderRoles(address) view returns (uint8)",
];

// Connect MetaMask and identify stakeholder
export const connectWallet = async () => {
  if (!window.ethereum) {
    throw new Error("MetaMask is not installed. Please install MetaMask.");
  }

  if (!CONTRACT_ADDRESS) {
    throw new Error("Smart contract address is not configured.");
  }

  const provider = new BrowserProvider(window.ethereum);

  const accounts = await provider.send("eth_requestAccounts", []);

  if (!accounts || accounts.length === 0) {
    throw new Error("No wallet account found.");
  }

  const address = getAddress(accounts[0]);

  const network = await provider.getNetwork();
  const chainId = Number(network.chainId);

  if (chainId !== REQUIRED_CHAIN_ID) {
    throw new Error(
      `Wrong network. Please connect to the required network (Chain ID: ${REQUIRED_CHAIN_ID}).`
    );
  }

  const signer = await provider.getSigner();

  const contract = new Contract(
    CONTRACT_ADDRESS,
    CONTRACT_ABI,
    provider
  );

  const roleValue = await contract.stakeholderRoles(address);
  const role = Number(roleValue);

  if (role === 0 || !ROLE_NAMES[role]) {
    throw new Error(
      "This wallet is not registered as an authorized stakeholder."
    );
  }

  return {
    address,
    chainId,
    provider,
    signer,
    role,
    roleName: ROLE_NAMES[role],
  };
};
