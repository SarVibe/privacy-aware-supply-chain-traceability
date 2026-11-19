import { Contract, isAddress } from "ethers";

const deployment = window.__PHARMACHAIN_DEPLOYMENT__ || {};
export const CONTRACT_ADDRESS = deployment.supplyChain || "";
export const EXPECTED_CHAIN_ID = BigInt(deployment.chainId || 131277322940537);

export const CONTRACT_ABI = [
  "function administrator() view returns (address)",
  "function stakeholderRoles(address) view returns (uint8)",
  "function setStakeholderRole(address stakeholder, uint8 role)",
  "function registerProduct(bytes32 commitment)",
  "function registerProduct(bytes32 commitment,bytes32[] qgramHashes)",
  "function fuzzyThresholdPercent() view returns (uint8)",
  "function setFuzzyThresholdPercent(uint8 threshold)",
  "function transferToDistributor(bytes32 commitment, address distributor)",
  "function acceptShipment(bytes32 commitment)",
  "function getProduct(bytes32 commitment) view returns (address manufacturer,address currentOwner,address pendingDistributor,uint64 createdBlock,uint64 bloomGroup,uint8 status,bool exists)",
  "function getProductCommitments() view returns (bytes32[])",
  "function mightContain(uint256 bloomGroup, bytes32 commitment) view returns (bool)",
  "function getQgramCandidateBlocks(bytes32[] queryQgramHashes,uint256 minimumMatches,uint256 firstBlockIndex,uint256 blockLimit) view returns (uint256[] candidateBlocks,uint256 totalBlocks)",
  "function verifyProof(bytes32 commitment,uint256[2] a,uint256[2][2] b,uint256[2] c,uint256[1] publicSignals) view returns (bool)",
  "event ProductRegistered(bytes32 indexed commitment,address indexed manufacturer,uint256 indexed blockNumber,uint256 bloomGroup)",
  "event ProductQgrams(bytes32 indexed commitment,uint256 indexed bloomGroup,uint256 indexed blockNumber,bytes32[] qgramHashes)",
  "event ShipmentInitiated(bytes32 indexed commitment,address indexed manufacturer,address indexed distributor)",
  "event ShipmentAccepted(bytes32 indexed commitment,address indexed distributor,uint256 timestamp)"
];

export function getContract(signerOrProvider) {
  if (!CONTRACT_ADDRESS || !/^0x[0-9a-fA-F]{40}$/.test(CONTRACT_ADDRESS)) {
    throw new Error("Contract deployment missing. Run the deployment steps in the README.");
  }
  return new Contract(CONTRACT_ADDRESS, CONTRACT_ABI, signerOrProvider);
}

export function isValidWalletAddress(value) {
  return isAddress(value);
}

export function shorten(value) {
  return value ? `${value.slice(0, 8)}...${value.slice(-6)}` : "—";
}

export const ROLE_NAMES = ["None", "Manufacturer", "Distributor"];
export const STATUS_NAMES = ["Registered", "In transit", "Delivered"];
