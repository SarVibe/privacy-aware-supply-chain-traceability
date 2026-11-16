"""
src/exact_matcher.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Baseline entity resolution engine using exact matching (SHA-256 cryptographic hash & strict string equality).
- Serves as the primary comparative baseline for Research Question 1 (RQ1).
- Demonstrates how traditional non-fuzzy supply chain ledgers fail under typographical noise (GIGO problem).
"""

import hashlib
from typing import Dict, List, Tuple, Optional
import pandas as pd
from src.preprocessor import TextPreprocessor


class ExactMatcher:
    """
    Baseline Exact Matching Engine.
    Clusters records based strictly on cryptographic hash equality of normalized text.
    """

    def __init__(self, normalize: bool = True):
        self.normalize = normalize
        self.hash_to_cluster: Dict[str, str] = {}
        self.cluster_records: Dict[str, List[dict]] = {}
        self.cluster_counter: int = 0

    def compute_hash(self, text: str) -> str:
        """Computes deterministic SHA-256 hash of a string."""
        if not text:
            return hashlib.sha256(b"").hexdigest()
        clean = TextPreprocessor.normalize(text) if self.normalize else text.strip()
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()
        
    def resolve_record(
        self,
        record_id: str,
        text: str,
        metadata: Optional[dict] = None
    ) -> Tuple[str, bool]:
        """
        Resolves an incoming record against stored exact hashes.

        Returns:
        - (cluster_id, is_new_cluster)
        """
        record_hash = self.compute_hash(text)
        meta = metadata or {}
        record_entry = {"record_id": record_id, "text": text, **meta}

        if record_hash in self.hash_to_cluster:
            cluster_id = self.hash_to_cluster[record_hash]
            self.cluster_records[cluster_id].append(record_entry)
            return cluster_id, False
        else:
            self.cluster_counter += 1
            cluster_id = f"EXACT_CLUSTER_{self.cluster_counter:04d}"
            self.hash_to_cluster[record_hash] = cluster_id
            self.cluster_records[cluster_id] = [record_entry]
            return cluster_id, True

    def process_dataset(
        self,
        df: pd.DataFrame,
        text_column: str = "raw_item_description",
        id_column: str = "record_id"
    ) -> pd.DataFrame:
        """
        Processes a full dataframe and assigns exact-match cluster IDs.
        """
        results = []
        for _, row in df.iterrows():
            rec_id = str(row[id_column])
            raw_text = str(row[text_column])

            cluster_id, is_new = self.resolve_record(
                record_id=rec_id,
                text=raw_text,
                metadata={"true_entity_id": row.get("true_entity_id", "")}
            )

            results.append({
                "record_id": rec_id,
                "true_entity_id": row.get("true_entity_id", ""),
                "predicted_cluster_id": cluster_id,
                "is_new_cluster": is_new,
                "record_hash": self.compute_hash(raw_text)
            })

        return pd.DataFrame(results)

    def reset(self):
        """Resets engine state between experiment trials."""
        self.hash_to_cluster.clear()
        self.cluster_records.clear()
        self.cluster_counter = 0


if __name__ == "__main__":
    matcher = ExactMatcher()

    # 1. Identical strings
    c1, is_new1 = matcher.resolve_record("R1", "didanosine 200mg videx tablets")
    c2, is_new2 = matcher.resolve_record("R2", "didanosine 200mg videx tablets")

    # 2. String with a single typographical error
    c3, is_new3 = matcher.resolve_record("R3", "didanosine 200mg videx tabblets")

    print("--- Exact Matcher Baseline Test ---")
    print(f"R1 ('videx tablets')  -> {c1} (New: {is_new1})")
    print(f"R2 ('videx tablets')  -> {c2} (New: {is_new2}) [Matches R1]")
    print(f"R3 ('videx tabblets') -> {c3} (New: {is_new3}) [FAILED TO MATCH due to typo]")