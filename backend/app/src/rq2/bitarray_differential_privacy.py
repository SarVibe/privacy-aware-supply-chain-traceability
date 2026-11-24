"""
src/differential_privacy.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Implements Local Differential Privacy (LDP) via Randomized Response bit-flipping on Bloom filters.
- Guarantees rigorous epsilon-LDP protection against frequency and bit-pattern inference attacks (RQ3).
- Mathematical formulation:
    Flip probability: p = 1.0 / (1.0 + exp(epsilon / 2.0))
    - When epsilon -> infinity: p -> 0.0 (No noise, identical to raw Bloom filter)
    - When epsilon = 1.0:       p ≈ 0.3775 (Balanced provable privacy and utility)
    - When epsilon -> 0:        p -> 0.5 (Maximum privacy, unbiased coin flip)
"""

from typing import Optional
import numpy as np
from bitarray import bitarray
from src.application_config import Config


class LocalDifferentialPrivacy:
    """
    Randomized Response Engine for Differentially Private Keyed Bloom Filters.
    """

    @staticmethod
    def calculate_flip_probability(epsilon: Optional[float]) -> float:
        """
        Calculates theoretical bit inversion probability p for a given privacy budget epsilon:
        p = 1 / (1 + exp(epsilon / 2))
        """
        if epsilon is None or epsilon <= 0.0:
            return 0.0
        # If epsilon is effectively infinite (No DP)
        if np.isinf(epsilon) or epsilon >= 50.0:
            return 0.0

        return float(1.0 / (1.0 + np.exp(epsilon / 2.0)))

    @classmethod
    def apply_randomized_response(
        cls,
        bf: bitarray,
        epsilon: Optional[float] = Config.DEFAULT_EPSILON,
        seed: Optional[int] = None
    ) -> bitarray:
        """
        Applies Randomized Response noise to a Bloom filter bitarray:
        For each bit b_i in bf:
            With probability p: b_i is flipped (0 -> 1, or 1 -> 0)
            With probability (1 - p): b_i remains unchanged

        Parameters:
        - bf: Input Keyed Bloom Filter bitarray.
        - epsilon: Privacy budget parameter (e.g., 0.5, 1.0, 2.0). If None, returns clone.
        - seed: Optional random seed for reproducible benchmark evaluations.

        Returns:
        - noisy_bf: Differential privacy protected bitarray.
        """
        if epsilon is None or epsilon <= 0.0 or np.isinf(epsilon):
            return bf.copy()

        p = cls.calculate_flip_probability(epsilon)
        if p == 0.0:
            return bf.copy()

        length = len(bf)
        rng = np.random.RandomState(seed) if seed is not None else np.random

        # Generate uniform random values across all bit positions
        random_values = rng.rand(length)

        # Boolean mask where bits should be flipped
        flip_mask = random_values < p

        # Fast C-level bitwise XOR flip with strict Big-Endian ordering
        flip_bits = bitarray(flip_mask.tolist(), endian="big")
        return bf ^ flip_bits

    @classmethod
    def batch_apply_ldp(
        cls,
        bf_list: list,
        epsilon: float,
        seed: Optional[int] = None
    ) -> list:
        """
        Applies LDP to a batch of Bloom filters sequentially, incrementing seeds
        if provided to maintain independent noise distributions.
        """
        noisy_list = []
        for idx, bf in enumerate(bf_list):
            current_seed = seed + idx if seed is not None else None
            noisy_list.append(cls.apply_randomized_response(bf, epsilon=epsilon, seed=current_seed))
        return noisy_list

    @classmethod
    def verify_empirical_flip_rate(
        cls,
        bf: bitarray,
        epsilon: float,
        trials: int = 1000
    ) -> dict:
        """
        Empirical validation helper for thesis/research paper:
        Runs multiple randomized response passes and compares empirical flip rate
        against theoretical probability p.
        """
        theoretical_p = cls.calculate_flip_probability(epsilon)
        total_bits = len(bf) * trials
        total_flipped = 0

        for _ in range(trials):
            noisy_bf = cls.apply_randomized_response(bf, epsilon=epsilon, seed=None)
            # Count positions where bits differ (XOR popcount)
            diff_count = (bf ^ noisy_bf).count(1)
            total_flipped += diff_count

        empirical_p = total_flipped / float(total_bits)
        error = abs(empirical_p - theoretical_p)

        return {
            "epsilon": epsilon,
            "theoretical_p": round(theoretical_p, 5),
            "empirical_p": round(empirical_p, 5),
            "absolute_error": round(error, 5)
        }
