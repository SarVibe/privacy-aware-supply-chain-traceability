
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


// Authenticate the connected wallet using a backend challenge and MetaMask signature.
export const signInWithWallet = async (wallet) => {
  // Request a unique authentication challenge from the backend.
  const nonceResponse = await fetch(
    `${import.meta.env.VITE_API_BASE_URL}/auth/nonce`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        wallet_address: wallet.address,
      }),
    }
  );

  // Reject unsuccessful challenge requests.
  if (!nonceResponse.ok) {
    throw new Error("Failed to request wallet authentication challenge.");
  }

  const nonceData = await nonceResponse.json();

  // Ask MetaMask to sign the exact message returned by the backend.
  const signature = await wallet.signer.signMessage(nonceData.message);

  // Send the wallet signature to the backend for verification.
  const verifyResponse = await fetch(
    `${import.meta.env.VITE_API_BASE_URL}/auth/verify`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        wallet_address: wallet.address,
        signature,
      }),
    }
  );

  // Reject unsuccessful signature verification.
  if (!verifyResponse.ok) {
    const errorData = await verifyResponse.json();
    throw new Error(errorData.detail || "Wallet authentication failed.");
  }

  // Return the backend-issued JWT and authenticated stakeholder details.
  return await verifyResponse.json();
};
