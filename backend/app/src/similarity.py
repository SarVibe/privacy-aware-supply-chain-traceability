"""
src/similarity.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- High-performance bitwise similarity engine for Bloom filter comparisons.
- Implements Dice Similarity coefficient: (2 * |bf1 & bf2|) / (|bf1| + |bf2|).
- Implements Jaccard Similarity for comparative baseline analysis.
- Supports batch candidate retrieval and matching against retrieved blockchain records.
"""

import os
from pathlib import Path
from typing import Dict, Tuple, Optional
from bitarray import bitarray
from dotenv import load_dotenv

# Search current directory, parent directory, and venv for .env
for p in [Path.cwd(), Path(__file__).resolve().parent.parent, Path(__file__).resolve().parent.parent.parent]:
    env_file = p / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
        break


class DiceSimilarityEngine:
    """
    Computes cryptographic similarity metrics over bit arrays with native bitwise efficiency.
    """

    DEFAULT_THRESHOLD = float(os.getenv("DEFAULT_SIMILARITY_THRESHOLD", 0.92))

    @staticmethod
    def calculate_dice(bf1: bitarray, bf2: bitarray) -> float:
        """
        Computes the Dice Similarity between two Bloom filter bit arrays:
        Dice(X, Y) = (2 * |X ∩ Y|) / (|X| + |Y|)

        Properties:
        - Symmetric: Dice(X, Y) == Dice(Y, X)
        - Range: [0.0, 1.0]
        - If both filters have zero bits set, returns 1.0 (exact match on empty).
        - If lengths mismatch, raises ValueError.
        """
        if len(bf1) != len(bf2):
            raise ValueError(
                f"Bitarray length mismatch: len(bf1)={len(bf1)} != len(bf2)={len(bf2)}"
            )

        # Bitwise AND popcount (C-level optimized)
        intersection_count = (bf1 & bf2).count(1)
        total_ones = bf1.count(1) + bf2.count(1)

        if total_ones == 0:
            return 1.0

        return (2.0 * intersection_count) / float(total_ones)

    @staticmethod
    def calculate_jaccard(bf1: bitarray, bf2: bitarray) -> float:
        """
        Computes the Jaccard Similarity between two Bloom filter bit arrays:
        Jaccard(X, Y) = |X ∩ Y| / |X ∪ Y|
        """
        if len(bf1) != len(bf2):
            raise ValueError("Bitarray length mismatch")

        intersection_count = (bf1 & bf2).count(1)
        union_count = (bf1 | bf2).count(1)

        if union_count == 0:
            return 1.0

        return float(intersection_count) / float(union_count)

    @classmethod
    def find_best_candidate(
        cls,
        incoming_bf: bitarray,
        stored_candidates: Dict[str, bitarray],
        threshold: Optional[float] = None
    ) -> Tuple[Optional[str], float]:
        """
        Finds the highest-scoring candidate that meets or exceeds the threshold tau.
        Returns (best_id, best_score) if score >= threshold, else (None, best_score).
        """
        if not stored_candidates:
            return None, 0.0

        tau = threshold if threshold is not None else cls.DEFAULT_THRESHOLD
        best_id: Optional[str] = None
        best_score: float = 0.0

        for candidate_id, candidate_bf in stored_candidates.items():
            score = cls.calculate_dice(incoming_bf, candidate_bf)
            if score > best_score:
                best_score = score
                best_id = candidate_id

        if best_score >= tau:
            return best_id, best_score

        return None, best_score


if __name__ == "__main__":
    from src.preprocessor import TextPreprocessor
    from src.keyed_bloom_filter import KeyedBloomFilter

    bf_engine = KeyedBloomFilter()

    # 1. Identical strings
    s1 = "Didanosine 200mg [Videx], tablets"
    s2 = "didanosine 200mg videx tablets"

    # 2. String with typo
    s3 = "didanosine 200mg videx tabblets"

    # 3. Hard negative (dosage difference: 60mg vs 600mg)
    s4 = "Abacavir/Lamivudine 60/30mg, tablets"
    s5 = "Abacavir/Lamivudine 600/300mg, tablets"

    def get_bf(text: str) -> bitarray:
        norm = TextPreprocessor.normalize(text)
        qg = TextPreprocessor.extract_token_qgrams(norm)
        return bf_engine.encode(qg)

    bf1 = get_bf(s1)
    bf2 = get_bf(s2)
    bf3 = get_bf(s3)
    bf4 = get_bf(s4)
    bf5 = get_bf(s5)

    dice_identical = DiceSimilarityEngine.calculate_dice(bf1, bf2)
    dice_typo = DiceSimilarityEngine.calculate_dice(bf2, bf3)
    dice_hard_neg = DiceSimilarityEngine.calculate_dice(bf4, bf5)

    print("--- Dice Similarity Engine Validation ---")
    print(f"Dice (Identical after Norm): {dice_identical:.4f} (Expected: 1.0000)")
    print(f"Dice (Minor Typo 'tabblets'): {dice_typo:.4f} (Expected: > 0.85)")
    print(f"Dice (Hard Negative 60 vs 600): {dice_hard_neg:.4f} (Expected: < tau={DiceSimilarityEngine.DEFAULT_THRESHOLD})")