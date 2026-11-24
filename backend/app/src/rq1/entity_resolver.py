"""
src/entity_resolver.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Executes Algorithm 1 Entity Resolution using Leader-based Incremental Clustering.
- Fixes Bit Saturation Bug: Preserves the canonical leader's Bloom filter without bitwise OR inflation.
- Evaluates incoming records against candidate clusters using Dice Similarity (tau >= 0.85).
- Dynamically assigns records to existing clusters or instantiates new canonical clusters.
"""

from typing import Dict, List, Tuple, Optional
from bitarray import bitarray
import numpy as np
import pandas as pd

from src.application_config import Config
from src.common.config import unit_interval
from src.common.encoding.versioned_bloom import BloomNamespace, IncompatibleBloomError, VersionedBloom
from src.common.similarity.dice import dice_matrix
from src.rq1.dice_similarity import DiceSimilarityEngine

FilterValue = bitarray | VersionedBloom


class ClusterEntity:
    """Represents a canonical entity cluster with an immutable leader Bloom filter."""

    def __init__(self, cluster_id: str, representative_bf: FilterValue, initial_record_id: str):
        self.cluster_id: str = cluster_id
        # Canonical Leader Filter (Fixed: Never inflated via bitwise OR)
        self.representative_bf = representative_bf.copy()
        self.member_record_ids: List[str] = [initial_record_id]
        self.record_count: int = 1

    def add_member(self, record_id: str, member_bf: FilterValue):
        """Appends member record without altering the leader filter."""
        del member_bf
        self.member_record_ids.append(record_id)
        self.record_count += 1


class EntityResolver:
    """
    Core Entity Resolution Engine for Algorithm 1.
    """

    def __init__(
        self,
        threshold: float = Config.DEFAULT_SIMILARITY_THRESHOLD,
        *,
        namespace: BloomNamespace | None = None,
    ):
        """
        Parameters:
        - threshold (tau): Minimum Dice similarity required to merge records (default: 0.85).
        """
        self.threshold = threshold if namespace is None else unit_interval(threshold, "tau")
        self.namespace = namespace
        self.clusters: Dict[str, ClusterEntity] = {}
        self.cluster_counter: int = 0

    def get_candidate_filters(self) -> Dict[str, FilterValue]:
        """
        Retrieves candidate filters from currently resolved clusters.
        Corresponds to Algorithm 1 Line 4: C <- retrieve_stored_records(Bp)
        """
        return {cid: entity.representative_bf for cid, entity in self.clusters.items()}

    def resolve_record(
        self,
        record_id: str,
        bf: FilterValue,
        metadata: Optional[dict] = None
    ) -> Tuple[str, float, bool]:
        """
        Executes Algorithm 1 Lines 4-24:
        - If candidate set C is empty -> Create new cluster (First record becomes Leader).
        - Else -> Find best candidate via Dice similarity.
        - If best_score >= tau -> Merge with best cluster.
        - Else -> Create new canonical cluster.

        Returns:
        - (assigned_cluster_id, best_score, is_new_cluster)
        """
        del metadata
        if self.namespace is not None:
            if not isinstance(bf, VersionedBloom):
                raise IncompatibleBloomError("Serving requires a versioned Bloom filter")
            bf.require_namespace(self.namespace)
        elif isinstance(bf, VersionedBloom):
            raise IncompatibleBloomError("Configure a namespace before resolving versioned filters")
        candidates = self.get_candidate_filters()

        # Empty candidate set: First record creates first cluster
        if not candidates:
            self.cluster_counter += 1
            cluster_id = f"CANONICAL_CLUSTER_{self.cluster_counter:04d}"
            self.clusters[cluster_id] = ClusterEntity(cluster_id, bf, record_id)
            return cluster_id, 0.0, True

        # Find best matching candidate
        if isinstance(bf, VersionedBloom):
            leaders = []
            for candidate in candidates.values():
                if not isinstance(candidate, VersionedBloom):
                    raise IncompatibleBloomError("Unversioned cluster representative")
                candidate.require_namespace(bf.namespace)
                leaders.append(candidate.bits)
            scores = dice_matrix(bf.bits[None, :], np.stack(leaders))[0]
            best_index = int(scores.argmax())
            best_cluster_id, best_score = list(candidates)[best_index], float(scores[best_index])
        else:
            best_cluster_id, best_score = DiceSimilarityEngine.find_best_candidate(
                incoming_bf=bf, stored_candidates=candidates, threshold=self.threshold
            )

        # Threshold check
        if best_cluster_id is not None and best_score >= self.threshold:
            self.clusters[best_cluster_id].add_member(record_id, bf)
            return best_cluster_id, best_score, False
        else:
            self.cluster_counter += 1
            cluster_id = f"CANONICAL_CLUSTER_{self.cluster_counter:04d}"
            self.clusters[cluster_id] = ClusterEntity(cluster_id, bf, record_id)
            return cluster_id, best_score, True

    def process_dataset(
        self,
        records: List[dict],
        bf_column: str = "bloom_filter",
        id_column: str = "record_id"
    ) -> pd.DataFrame:
        """
        Harmonizes a batch of multi-party records sequentially.
        """
        results = []
        for rec in records:
            rec_id = str(rec[id_column])
            bf = rec[bf_column]

            cluster_id, score, is_new = self.resolve_record(
                record_id=rec_id,
                bf=bf,
                metadata=rec
            )

            results.append({
                "record_id": rec_id,
                "true_entity_id": rec.get("true_entity_id", ""),
                "predicted_cluster_id": cluster_id,
                "similarity_score": round(score, 4),
                "is_new_cluster": is_new
            })

        return pd.DataFrame(results)

    def reset(self):
        """Resets clustering state between experiment trials."""
        self.clusters.clear()
        self.cluster_counter = 0
