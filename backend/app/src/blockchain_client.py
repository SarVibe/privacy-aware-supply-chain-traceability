"""
src/blockchain_client.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Web3.py interface connecting Python Harmonization Pipeline to the Ethereum Smart Contract.
- Implements Algorithm 1 Line 4: Candidates C <- retrieve_stored_records(Bp).
- Implements Algorithm 1 Lines 21-22: Commit tuple <B, ClusterID, Hash, Time> on-chain.
- Accurately tracks On-chain Gas Consumption and Transaction Latency for Scalability Benchmarks.
"""

import os
import json
import time
import logging
import threading

# Ensure inaccessible SSLKEYLOGFILE doesn't trigger PermissionError in ssl context
if "SSLKEYLOGFILE" in os.environ:
    try:
        with open(os.environ["SSLKEYLOGFILE"], "a"):
            pass
    except (PermissionError, OSError):
        del os.environ["SSLKEYLOGFILE"]

from typing import Dict, List, Optional, Any
from bitarray import bitarray
# pyrefly: ignore[missing-import]
from web3 import Web3

from src.config import Config
from src.keyed_bloom_filter import KeyedBloomFilter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class BlockchainClient:
    """
    Manages Web3 connectivity, on-chain state queries, and transaction dispatch for C1.
    """

    def __init__(
        self,
        rpc_url: str = Config.BLOCKCHAIN_RPC_URL,
        contract_address: str = Config.CONTRACT_ADDRESS,
        private_key: str = Config.BLOCKCHAIN_PRIVATE_KEY,
        chain_id: int = Config.CHAIN_ID,
        bf_length: int = Config.DEFAULT_BF_LENGTH,
        allow_mock_ledger: bool = Config.ALLOW_MOCK_LEDGER
    ):
        self.rpc_url = rpc_url
        self.contract_address = Web3.to_checksum_address(contract_address) if contract_address.startswith("0x") else contract_address
        self.private_key = private_key
        self.chain_id = chain_id
        self.bf_length = bf_length
        if self.bf_length <= 0 or self.bf_length % 8 != 0:
            raise ValueError("bf_length must be a positive multiple of 8.")
        self.expected_bloom_filter_bytes = self.bf_length // 8
        self.allow_mock_ledger = allow_mock_ledger
        self._transaction_lock = threading.Lock()

        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.is_live = False
        self.contract = None
        self.account = None

        # In-memory mock ledger fallback if local RPC node is offline
        self._mock_records: List[Dict[str, Any]] = []
        self._mock_cluster_leaders: Dict[str, bitarray] = {}
        self._mock_existing_hashes: set = set()

        self._initialize_connection()

    def _initialize_connection(self):
        """Attempts connection to the EVM RPC node and checks contract deployment."""
        try:
            if self.w3.is_connected():
                if not self.private_key:
                    raise ValueError("BLOCKCHAIN_PRIVATE_KEY is required for a live connection.")
                self.account = self.w3.eth.account.from_key(self.private_key)

                network_chain_id = self.w3.eth.chain_id
                if network_chain_id != self.chain_id:
                    raise ValueError(
                        f"RPC chain ID {network_chain_id} does not match configured "
                        f"chain ID {self.chain_id}."
                    )

                artifact_path = (
                    Config.PROJECT_ROOT
                    / "blockchain"
                    / "artifacts"
                    / "contracts"
                    / "HarmonizedSupplyChain.sol"
                    / "HarmonizedSupplyChain.json"
                )
                if not artifact_path.exists():
                    raise FileNotFoundError(
                        f"Contract artifact not found at {artifact_path}. "
                        "Run 'npm run compile' from the blockchain directory."
                    )
                with open(artifact_path, "r", encoding="utf-8") as f:
                    contract_abi = json.load(f)["abi"]

                self.contract = self.w3.eth.contract(
                    address=self.contract_address,
                    abi=contract_abi
                )

                deployed_filter_bytes = self.contract.functions.bloomFilterBytes().call()
                if deployed_filter_bytes != self.expected_bloom_filter_bytes:
                    raise ValueError(
                        f"Contract expects {deployed_filter_bytes} Bloom-filter bytes, "
                        f"but client is configured for {self.expected_bloom_filter_bytes}."
                    )

                # Verify that contract code actually exists at the deployed address
                code = self.w3.eth.get_code(self.contract_address)
                if code in (b'', b'\x00', b'0x', '0x'):
                    logger.warning(
                        f"No contract bytecode found at {self.contract_address}. "
                        f"Operating in High-Fidelity Mock Ledger mode. "
                        f"(Run 'node blockchain/scripts/deploy.js' after starting the local node)."
                    )
                    raise ValueError(
                        f"No contract bytecode found at {self.contract_address}."
                    )

                self.is_live = True
                logger.info(f"Connected to Blockchain RPC: {self.rpc_url} | Contract: {self.contract_address} | Account: {self.account.address}")
            else:
                logger.warning(f"RPC {self.rpc_url} unreachable. Operating in High-Fidelity Mock Ledger mode.")
        except Exception as e:
            if self.allow_mock_ledger:
                logger.warning(
                    f"Blockchain init exception ({e}). Operating in explicit mock mode."
                )
            else:
                logger.error(f"Blockchain initialization failed: {e}")

    def _to_bytes32(self, hash_val: str) -> bytes:
        """Converts an exact 32-byte hexadecimal hash into bytes."""
        clean = hash_val[2:] if hash_val.startswith("0x") else hash_val
        if len(clean) != 64:
            raise ValueError("record_hash_hex must contain exactly 32 bytes.")
        try:
            return bytes.fromhex(clean)
        except ValueError as exc:
            raise ValueError("record_hash_hex must be hexadecimal.") from exc

    def retrieve_stored_candidates(self, use_leader_only: bool = True) -> Dict[str, bitarray]:
        """
        Algorithm 1 Line 4: C <- retrieve_stored_records(Bp)
        Fetches existing Bloom filters from the ledger via a zero-gas view call.

        Returns:
        - Dict mapping {cluster_id: bitarray}
        """
        candidate_map: Dict[str, bitarray] = {}

        if self.is_live:
            try:
                if use_leader_only:
                    c_ids, filters = self.contract.functions.getClusterLeaders().call()
                    for c_id, raw_bytes in zip(c_ids, filters):
                        candidate_map[c_id] = KeyedBloomFilter.from_bytes(raw_bytes, length=self.bf_length)
                else:
                    candidates = self.contract.functions.getCandidateRecords().call()
                    for cand in candidates:
                        rec_id, c_id, raw_bytes = cand[0], cand[1], cand[2]
                        candidate_map[rec_id] = KeyedBloomFilter.from_bytes(raw_bytes, length=self.bf_length)
                return candidate_map
            except Exception as e:
                logger.error(f"Failed to query on-chain candidates: {e}")
                if not self.allow_mock_ledger:
                    raise RuntimeError("Unable to query the live blockchain.") from e

        # Mock fallback state
        if not self.allow_mock_ledger:
            raise RuntimeError("Blockchain is unavailable and mock ledger is disabled.")
        if use_leader_only:
            return {c_id: bf.copy() for c_id, bf in self._mock_cluster_leaders.items()}
        else:
            return {r["record_id"]: r["bloom_filter"].copy() for r in self._mock_records}

    def _get_fee_fields(self) -> Dict[str, int]:
        """Returns EIP-1559 fee fields when supported, otherwise legacy gas price."""
        latest_block = self.w3.eth.get_block("latest")
        base_fee = latest_block.get("baseFeePerGas")
        if base_fee is not None:
            priority_fee = self.w3.eth.max_priority_fee
            return {
                "maxPriorityFeePerGas": priority_fee,
                "maxFeePerGas": base_fee * 2 + priority_fee,
            }
        return {"gasPrice": self.w3.eth.gas_price}

    def commit_harmonized_record(
        self,
        record_id: str,
        cluster_id: str,
        bf: bitarray,
        record_hash_hex: str
    ) -> Dict[str, Any]:
        """
        Algorithm 1 Lines 21-22:
        Commits tuple <B_pi, Cluster_ID, Hash, Timestamp> to the ledger.

        Returns:
        - Dict containing transaction receipt, gas used, latency in ms, and status.
        """
        start_time = time.time()
        if not record_id:
            raise ValueError("record_id cannot be empty.")
        if not cluster_id:
            raise ValueError("cluster_id cannot be empty.")
        if len(bf) != self.bf_length:
            raise ValueError(
                f"Bloom filter length {len(bf)} does not match configured "
                f"length {self.bf_length}."
            )
        bf_bytes = KeyedBloomFilter.to_bytes(bf)
        if len(bf_bytes) != self.expected_bloom_filter_bytes:
            raise ValueError("Serialized Bloom filter length is invalid.")
        record_hash_bytes32 = self._to_bytes32(record_hash_hex)

        if self.is_live:
            try:
                with self._transaction_lock:
                    nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
                    transaction_call = self.contract.functions.storeHarmonizedRecord(
                        record_id,
                        cluster_id,
                        bf_bytes,
                        record_hash_bytes32
                    )
                    gas_limit = int(transaction_call.estimate_gas({"from": self.account.address}) * 1.25)
                    fee_fields = self._get_fee_fields()
                    tx = transaction_call.build_transaction({
                        "chainId": self.chain_id,
                        "gas": gas_limit,
                        "nonce": nonce,
                        **fee_fields
                    })
                    signed_tx = self.w3.eth.account.sign_transaction(
                        tx, private_key=self.private_key
                    )
                    tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                    receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=10)

                latency_ms = (time.time() - start_time) * 1000.0

                if receipt.status == 1:
                    return {
                        "status": "SUCCESS",
                        "tx_hash": tx_hash.hex(),
                        "gas_used": receipt.gasUsed,
                        "latency_ms": round(latency_ms, 2),
                        "block_number": receipt.blockNumber,
                        "is_live_chain": True
                    }
                else:
                    logger.error(f"On-chain transaction reverted: tx_hash={tx_hash.hex()}")
                    return {
                        "status": "REVERTED",
                        "tx_hash": tx_hash.hex(),
                        "gas_used": receipt.gasUsed,
                        "latency_ms": round(latency_ms, 2),
                        "block_number": receipt.blockNumber,
                        "is_live_chain": True
                    }
            except Exception as e:
                logger.error(f"On-chain transaction failed: {e}")
                return {
                    "status": "FAILED",
                    "error": str(e),
                    "latency_ms": round((time.time() - start_time) * 1000.0, 2),
                    "is_live_chain": True
                }

        if not self.allow_mock_ledger:
            return {
                "status": "BLOCKCHAIN_UNAVAILABLE",
                "error": "Live blockchain is unavailable and mock ledger is disabled.",
                "latency_ms": round((time.time() - start_time) * 1000.0, 2),
                "is_live_chain": False
            }

        # Mock fallback commitment
        time.sleep(0.005)  # Simulate 5ms local transaction latency
        latency_ms = (time.time() - start_time) * 1000.0

        # Faithful duplicate prevention in mock mode (mirrors Solidity require(!existingRecordHashes))
        if record_hash_hex in self._mock_existing_hashes:
            logger.warning(f"Mock Ledger: Record hash {record_hash_hex[:16]}... already committed. Reverting transaction.")
            return {
                "status": "REVERTED_MOCK",
                "tx_hash": "N/A",
                "gas_used": 21000,
                "latency_ms": round(latency_ms, 2),
                "block_number": len(self._mock_records),
                "is_live_chain": False
            }

        is_new_cluster = cluster_id not in self._mock_cluster_leaders
        self._mock_existing_hashes.add(record_hash_hex)
        self._mock_records.append({
            "record_id": record_id,
            "cluster_id": cluster_id,
            "bloom_filter": bf.copy(),
            "record_hash": record_hash_hex,
            "timestamp": int(time.time())
        })
        if is_new_cluster:
            self._mock_cluster_leaders[cluster_id] = bf.copy()

        # Simulated empirical gas cost: ~92k base, ~500k on new cluster leader initialization
        simulated_gas = 501138 if is_new_cluster else 92450

        return {
            "status": "SUCCESS_MOCK",
            "tx_hash": f"0xmock_{int(time.time()*1000):x}",
            "gas_used": simulated_gas,
            "latency_ms": round(latency_ms, 2),
            "block_number": len(self._mock_records),
            "is_live_chain": False
        }

    def verify_record_exists(self, record_hash_hex: str) -> bool:
        """
        Verification helper (for Component 4 integration).
        Checks if a given SHA-256 record hash is registered on the ledger.
        """
        if self.is_live:
            try:
                record_hash_bytes32 = self._to_bytes32(record_hash_hex)
                return self.contract.functions.verifyRecordExists(record_hash_bytes32).call()
            except Exception as e:
                logger.error(f"Error calling verifyRecordExists: {e}")
                if not self.allow_mock_ledger:
                    raise RuntimeError("Unable to verify the record on the live blockchain.") from e

        if not self.allow_mock_ledger:
            raise RuntimeError("Blockchain is unavailable and mock ledger is disabled.")
        return record_hash_hex in self._mock_existing_hashes

    def get_record(self, index: int) -> Optional[Dict[str, Any]]:
        """
        Fetches full record details by record index from the ledger.
        """
        if self.is_live:
            try:
                rec = self.contract.functions.getRecord(index).call()
                return {
                    "record_id": rec[0],
                    "cluster_id": rec[1],
                    "bloom_filter": KeyedBloomFilter.from_bytes(rec[2], length=self.bf_length),
                    "record_hash": rec[3].hex(),
                    "timestamp": rec[4],
                    "submitted_by": rec[5]
                }
            except Exception as e:
                logger.error(f"Error fetching record index {index} on-chain: {e}")
                if not self.allow_mock_ledger:
                    raise RuntimeError("Unable to fetch the record from the live blockchain.") from e

        if not self.allow_mock_ledger:
            raise RuntimeError("Blockchain is unavailable and mock ledger is disabled.")
        if 0 <= index < len(self._mock_records):
            return self._mock_records[index]
        return None

    def reset_mock_state(self):
        """Resets mock ledger state for isolated test executions."""
        self._mock_records.clear()
        self._mock_cluster_leaders.clear()
        self._mock_existing_hashes.clear()

    def get_ledger_summary(self) -> Dict[str, int]:
        """Returns total records and clusters currently stored."""
        if self.is_live:
            try:
                tot_rec = self.contract.functions.getTotalRecords().call()
                tot_clu = self.contract.functions.getTotalClusters().call()
                return {"total_records": tot_rec, "total_clusters": tot_clu}
            except Exception as e:
                logger.error(f"Error fetching ledger summary on-chain: {e}")
                if not self.allow_mock_ledger:
                    raise RuntimeError("Unable to fetch the live ledger summary.") from e
        if not self.allow_mock_ledger:
            raise RuntimeError("Blockchain is unavailable and mock ledger is disabled.")
        return {
            "total_records": len(self._mock_records),
            "total_clusters": len(self._mock_cluster_leaders)
        }


if __name__ == "__main__":
    from src.preprocessor import TextPreprocessor

    client = BlockchainClient()
    bf_engine = KeyedBloomFilter(length=Config.DEFAULT_BF_LENGTH, num_hashes=Config.DEFAULT_NUM_HASHES)

    sample_desc = "Didanosine 200mg [Videx], tablets"
    norm = TextPreprocessor.normalize(sample_desc)
    qg = TextPreprocessor.extract_token_qgrams(norm, q=Config.DEFAULT_Q)
    test_bf = bf_engine.encode(qg)
    test_hash = Web3.keccak(text=sample_desc).hex()

    print("--- Blockchain Client Test ---")
    print(f"Network Status: {'LIVE RPC' if client.is_live else 'MOCK FALLBACK'}")
    
    # 1. Commit record
    res = client.commit_harmonized_record("REC_TEST_01", "CANONICAL_CLUSTER_0001", test_bf, test_hash)
    print(f"Commit Status:   {res['status']} | Gas Used: {res['gas_used']} | Latency: {res['latency_ms']} ms")

    # 2. Test duplicate replay prevention
    res_dup = client.commit_harmonized_record("REC_TEST_02", "CANONICAL_CLUSTER_0001", test_bf, test_hash)
    print(f"Duplicate Check: {res_dup['status']} (Expected: REVERTED / REVERTED_MOCK)")

    # 3. Retrieve candidates
    candidates = client.retrieve_stored_candidates(use_leader_only=True)
    print(f"Retrieved Clusters: {len(candidates)} clusters found on ledger.")
    print(f"Verify Record Exists ({test_hash[:10]}...): {client.verify_record_exists(test_hash)}")
    print(f"Ledger Summary:  {client.get_ledger_summary()}")