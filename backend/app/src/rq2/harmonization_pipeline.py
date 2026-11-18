""""
src/harmonization_pipeline.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Master orchestration engine implementing Algorithm 1 end-to-end.
- Ingests raw multi-stakeholder pharmaceutical records.
- Normalizes and tokenizes text into q-grams (q=3).
- Generates Keyed Bloom Filters (with optional epsilon-LDP noise injection).
- Retrieves stored cluster candidates from Blockchain (Algorithm 1 Line 4).
- Resolves canonical clusters via Dice Similarity (tau >= 0.85).
- Commits final 4-tuple to Blockchain ledger (Algorithm 1 Lines 21-22).
"""

import time
import hashlib
import logging
from typing import Dict, Optional, Any
import pandas as pd

from src.config import Config
from src.common.preprocessor import TextPreprocessor
from src.common.keyed_bloom_filter import KeyedBloomFilter
from src.common.differential_privacy import LocalDifferentialPrivacy
from src.rq1.entity_resolver import EntityResolver
from src.blockchain_client import BlockchainClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class HarmonizationPipeline:
    """
    End-to-End Pre-Ledger Harmonization Pipeline executing Algorithm 1.
    """

    def __init__(
        self,
        length: int = Config.DEFAULT_BF_LENGTH,
        num_hashes: int = Config.DEFAULT_NUM_HASHES,
        threshold: float = Config.DEFAULT_SIMILARITY_THRESHOLD,
        q: int = Config.DEFAULT_Q,
        epsilon: Optional[float] = None,  # None means Raw Keyed Bloom Filter (No DP)
        enable_blockchain_commit: bool = True
    ):
        self.length = length
        self.num_hashes = num_hashes
        self.threshold = threshold
        self.q = q
        self.epsilon = epsilon
        self.enable_blockchain_commit = enable_blockchain_commit

        # Initialize sub-modules
        self.bf_engine = KeyedBloomFilter(length=self.length, num_hashes=self.num_hashes)
        self.resolver = EntityResolver(threshold=self.threshold)
        self.blockchain = BlockchainClient(bf_length=self.length)
        self._ledger_synchronized = False
        if self.enable_blockchain_commit:
            self.synchronize_with_ledger()

    def synchronize_with_ledger(self):
        """
        Syncs local resolver state with stored cluster leaders from the blockchain.
        Corresponds to initial candidate state loading for Algorithm 1 Line 4.
        """
        import re
        stored_candidates = self.blockchain.retrieve_stored_candidates(use_leader_only=True)
        for cluster_id, leader_bf in stored_candidates.items():
            if cluster_id not in self.resolver.clusters:
                # Seed cluster entity from on-chain state and track highest numerical cluster counter
                match = re.search(r"(\d+)$", cluster_id)
                if match:
                    numeric_id = int(match.group(1))
                    self.resolver.cluster_counter = max(self.resolver.cluster_counter, numeric_id)
                else:
                    self.resolver.cluster_counter += 1
                from src.rq1.entity_resolver import ClusterEntity
                self.resolver.clusters[cluster_id] = ClusterEntity(
                    cluster_id=cluster_id,
                    representative_bf=leader_bf,
                    initial_record_id=f"ONCHAIN_{cluster_id}"
                )
        self._ledger_synchronized = True
        logger.info(f"Synchronized with Ledger: {len(self.resolver.clusters)} active clusters loaded.")

    def process_single_record(
        self,
        record_id: str,
        raw_description: str,
        true_entity_id: str = "",
        stakeholder_org: str = "Generic_Org",
        dosage: Optional[str] = None,
        dosage_form: Optional[str] = None,
        pack_size: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Harmonizes a single incoming supply chain record through Algorithm 1.
        Uses Composite Multi-Attribute Representation: Tag(Name) ∪ Tag(Dosage) ∪ Tag(Dosage Form) ∪ Tag(Pack Size).
        """
        if not record_id or not record_id.strip():
            raise ValueError("record_id cannot be empty.")
        if not isinstance(raw_description, str) or not raw_description.strip():
            raise ValueError("raw_description cannot be empty.")
        if self.enable_blockchain_commit and not self._ledger_synchronized:
            self.synchronize_with_ledger()
        start_time = time.time()

        # Step 1: Composite Multi-Attribute Preprocessing
        composite_qgrams = TextPreprocessor.extract_composite_qgrams(
            text=raw_description,
            dosage=dosage,
            dosage_form=dosage_form,
            pack_size=pack_size,
            q=self.q
        )

        # Step 2: Keyed Bloom Filter Generation
        raw_bf = self.bf_engine.encode(composite_qgrams)

        # Step 3: Optional Local Differential Privacy (Randomized Response)
        if self.epsilon is not None and self.epsilon > 0:
            active_bf = LocalDifferentialPrivacy.apply_randomized_response(
                raw_bf, epsilon=self.epsilon, seed=None
            )
        else:
            active_bf = raw_bf

        # Step 4: Off-Chain / Pre-Ledger Entity Resolution (Lines 8-20)
        assigned_cluster_id, best_score, is_new_cluster = self.resolver.resolve_record(
            record_id=record_id,
            bf=active_bf,
            metadata={"raw_description": raw_description, "true_entity_id": true_entity_id}
        )

        preledger_latency_ms = (time.time() - start_time) * 1000.0

        # Compute SHA-256 Hash of raw metadata bound to record_id and org to guarantee uniqueness across identical drugs
        record_hash = hashlib.sha256(f"{record_id}|{raw_description}|{stakeholder_org}".encode("utf-8")).hexdigest()

        # Step 5: On-Chain Commitment (Lines 21-22)
        onchain_result = None
        if self.enable_blockchain_commit:
            onchain_result = self.blockchain.commit_harmonized_record(
                record_id=record_id,
                cluster_id=assigned_cluster_id,
                bf=active_bf,
                record_hash_hex=record_hash
            )
            if onchain_result["status"] not in {"SUCCESS", "SUCCESS_MOCK"}:
                raise RuntimeError(
                    f"Blockchain commitment failed for record {record_id}: "
                    f"{onchain_result.get('error', onchain_result['status'])}"
                )

        total_latency_ms = (time.time() - start_time) * 1000.0

        return {
            "record_id": record_id,
            "true_entity_id": true_entity_id,
            "predicted_cluster_id": assigned_cluster_id,
            "similarity_score": round(best_score, 4),
            "is_new_cluster": is_new_cluster,
            "stakeholder_org": stakeholder_org,
            "preledger_latency_ms": round(preledger_latency_ms, 2),
            "total_latency_ms": round(total_latency_ms, 2),
            "gas_used": onchain_result["gas_used"] if onchain_result else 0,
            "tx_hash": onchain_result["tx_hash"] if onchain_result else "N/A",
            "onchain_status": onchain_result["status"] if onchain_result else "NOT_COMMITTED"
        }

    def process_batch(self, df_records: pd.DataFrame) -> pd.DataFrame:
        """
        Sequentially harmonizes a stream of records from a DataFrame.
        """
        results = []
        logger.info(f"Commencing batch harmonization for {len(df_records):,} records...")

        for idx, row in df_records.iterrows():
            rec_id = str(row.get("record_id", f"REC_{idx+1:05d}"))
            raw_desc = str(row.get("raw_item_description", row.get("Item Description", "")))
            dose = row.get("dosage", None)
            form = row.get("dosage_form", None)
            pack = row.get("pack_size", None)
            true_id = str(row.get("true_entity_id", ""))
            org = str(row.get("stakeholder_org", row.get("vendor", "Org_SupplyChain")))

            res = self.process_single_record(
                record_id=rec_id,
                raw_description=raw_desc,
                true_entity_id=true_id,
                stakeholder_org=org,
                dosage=dose,
                dosage_form=form,
                pack_size=pack
            )
            results.append(res)

            if (idx + 1) % 100 == 0 or (idx + 1) == len(df_records):
                logger.info(f"Processed {idx + 1}/{len(df_records)} records...")

        return pd.DataFrame(results)

    def reset(self):
        """Resets in-memory clustering engine."""
        self.resolver.reset()
        self._ledger_synchronized = False
        if self.enable_blockchain_commit:
            self.synchronize_with_ledger()


if __name__ == "__main__":
    pipeline = HarmonizationPipeline(enable_blockchain_commit=True)
    pipeline.synchronize_with_ledger()

    test_sample = [
        {"id": "R01", "desc": "Didanosine 200mg [Videx], tablets", "true_id": "ENTITY_0001"},
        {"id": "R02", "desc": "didanosine 200mg videx tabblets", "true_id": "ENTITY_0001"},
        {"id": "R03", "desc": "Abacavir/Lamivudine 600/300mg, tablets", "true_id": "ENTITY_0002"},
    ]

    for item in test_sample:
        out = pipeline.process_single_record(item["id"], item["desc"], item["true_id"])
        print(f"[{out['record_id']}] -> Cluster: {out['predicted_cluster_id']} | Score: {out['similarity_score']} | Gas: {out['gas_used']} | Latency: {out['total_latency_ms']} ms")