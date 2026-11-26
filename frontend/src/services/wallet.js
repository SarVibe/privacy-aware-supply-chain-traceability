
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

const CONTRACT_ABI = [
  "function stakeholderRoles(address) view returns (uint8)",
  "function storeRecord(uint256[10] commitments) returns (uint256)",
  "function verifySupplyChain(uint256 recordId, uint256[2] _pA, uint256[2][2] _pB, uint256[2] _pC)",
  "event RecordStored(uint256 indexed recordId, address indexed manufacturer, uint256 timestamp)",
];

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

  const role = Number(await contract.stakeholderRoles(address));

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

export const signInWithWallet = async (wallet) => {
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

  if (!nonceResponse.ok) {
    throw new Error("Failed to request wallet authentication challenge.");
  }

  const nonceData = await nonceResponse.json();
  const signature = await wallet.signer.signMessage(nonceData.message);

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

  if (!verifyResponse.ok) {
    const errorData = await verifyResponse.json();
    throw new Error(errorData.detail || "Wallet authentication failed.");
  }

  return await verifyResponse.json();
};

// Store the manufacturer's ten commitments on-chain.
export const storeRecordOnChain = async (wallet, commitments) => {
  if (!wallet?.signer) {
    throw new Error("MetaMask wallet is not connected.");
  }

  if (wallet.role !== 2) {
    throw new Error("Only Manufacturers can store records.");
  }

  if (!Array.isArray(commitments) || commitments.length !== 10) {
    throw new Error("Exactly 10 attribute commitments are required.");
  }

  const contract = new Contract(
    CONTRACT_ADDRESS,
    CONTRACT_ABI,
    wallet.signer
  );

  const transaction = await contract.storeRecord(commitments);
  const receipt = await transaction.wait();

  if (!receipt || receipt.status !== 1) {
    throw new Error("Record storage transaction failed.");
  }

  let recordId = null;

  for (const log of receipt.logs) {
    try {
      const parsed = contract.interface.parseLog(log);

      if (parsed?.name === "RecordStored") {
        recordId = parsed.args.recordId.toString();
        break;
      }
    } catch {
      // Ignore unrelated contract events.
    }
  }

  if (recordId === null) {
    throw new Error("RecordStored event was not found.");
  }

  return {
    transactionHash: receipt.hash,
    recordId,
    blockNumber: receipt.blockNumber,
    gasUsed: receipt.gasUsed.toString(),
    status: "success",
  };
};

// Submit selective ZKP verification through the stakeholder's MetaMask wallet.
export const submitZKPVerification = async (wallet, recordId, proof) => {
  if (!wallet?.signer) {
    throw new Error("MetaMask wallet is not connected.");
  }

  if (!recordId || !proof?.pi_a || !proof?.pi_b || !proof?.pi_c) {
    throw new Error("Record ID or Groth16 proof is missing.");
  }

  const contract = new Contract(
    CONTRACT_ADDRESS,
    CONTRACT_ABI,
    wallet.signer
  );

  const pA = [
    proof.pi_a[0],
    proof.pi_a[1],
  ];

  const pB = [
    [proof.pi_b[0][1], proof.pi_b[0][0]],
    [proof.pi_b[1][1], proof.pi_b[1][0]],
  ];

  const pC = [
    proof.pi_c[0],
    proof.pi_c[1],
  ];

  const transaction = await contract.verifySupplyChain(
    recordId,
    pA,
    pB,
    pC
  );

  const receipt = await transaction.wait();

  if (!receipt || receipt.status !== 1) {
    throw new Error("Blockchain verification transaction failed.");
  }

  return {
    transactionHash: receipt.hash,
    blockNumber: receipt.blockNumber,
    gasUsed: receipt.gasUsed.toString(),
    status: "success",
  };
};
