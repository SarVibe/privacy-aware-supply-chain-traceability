"""Aggregate frequency-alignment and collision diagnostics on prepared RQ2 cohorts."""

from collections import Counter
from dataclasses import dataclass
from math import expm1, log2

import numpy as np

from src.common.encoding.bloom_filter import BloomFilterEncoder, fill_ratio
from src.common.seeding import make_rng
from src.rq2.collision_config import Controls


def insertion_frequencies(records: list[set[str]]) -> dict[str, float]:
    counts = Counter(gram for record in records for gram in record)
    return {gram: counts[gram] / len(records) for gram in sorted(counts)}


def expected_occupancy(q_mean: float, length: int, hashes: int) -> float:
    return -expm1(-hashes * q_mean / length)


def fingerprint_collision_proxy(q_mean: float, length: int, hashes: int) -> float:
    return expected_occupancy(q_mean, length, hashes) ** hashes


@dataclass(frozen=True)
class FrequencyEvaluation:
    """Evaluator state. Exports only aggregate statistics."""

    bit_frequency: np.ndarray
    universe: tuple[str, ...]
    membership: np.ndarray

    @classmethod
    def from_records(cls, bits, target, auxiliary, encoder: BloomFilterEncoder):
        universe = tuple(sorted(target.keys() | auxiliary.keys()))
        membership = np.zeros((len(universe), bits.shape[1]), dtype=bool)
        membership[np.arange(len(universe))[:, None], encoder.gram_positions(universe)] = True
        if not universe or not bits.any():
            raise ValueError("Frequency evaluation needs at least one insertion token and one set bit")
        return cls(bits.mean(axis=0), universe, membership)

    @property
    def used(self) -> np.ndarray:
        return np.flatnonzero(self.bit_frequency)

    @property
    def baseline(self) -> float:
        return float(self.membership[:, self.used].mean())

    def alignment_metrics(self, reference: dict[str, float], seed: int, purpose: str) -> dict:
        """Match midpoint quantiles of ascending document frequencies, using seeded tie breaks."""
        if not reference:
            raise ValueError("Frequency alignment needs a nonempty auxiliary token population")
        rng = make_rng(seed, purpose)
        candidates = [index for index, token in enumerate(self.universe) if token in reference]
        token_frequency = [reference[self.universe[index]] for index in candidates]
        ordered_tokens = np.asarray(candidates)[np.lexsort((rng.random(len(candidates)), token_frequency))]
        used = self.used
        ordered_bits = used[np.lexsort((rng.random(len(used)), self.bit_frequency[used]))]
        ranks = ((np.arange(len(used)) + 0.5) * len(ordered_tokens) / len(used)).astype(int)
        score = float(self.membership[ordered_tokens[ranks], ordered_bits].mean())
        baseline = self.baseline
        return {"attack_success": score, "random_baseline": baseline, "lift": score / baseline,
                "used_bits": len(used)}

    def control_row(self, reference: dict[str, float], seed: int, split: str, settings: Controls) -> dict:
        result = self.alignment_metrics(reference, seed, f"rq2:control-positive:{split}")
        used = self.used
        rng = make_rng(seed, f"rq2:control-negative:{split}")
        random_alignment = rng.integers(len(self.universe), size=(settings.permutations, len(used)))
        random_mean = float(self.membership[random_alignment, used].mean())
        gap = abs(random_mean - result["random_baseline"])
        return {
            "seed": seed, "split": split, "l": settings.positive[0], "k": settings.positive[1], **result,
            "min_lift": settings.min_lift, "permutations": settings.permutations,
            "random_control_mean": random_mean, "random_gap": gap, "max_random_gap": settings.max_random_gap,
            "passed": result["lift"] >= settings.min_lift and gap <= settings.max_random_gap,
        }

    def structural_metrics(self, bits, records: list[set[str]], hashes: int) -> dict:
        counts = np.fromiter(map(len, records), dtype=int)
        q_mean = float(counts.mean())
        fill = float(fill_ratio(bits).mean())
        length = bits.shape[1]
        proxy = fingerprint_collision_proxy(q_mean, length, hashes)
        ambiguity = self.membership.sum(axis=0)
        entropy = -fill * log2(fill) - (1 - fill) * log2(1 - fill) if 0 < fill < 1 else 0.0
        return {
            "fill": fill, "fill_expected": expected_occupancy(q_mean, length, hashes), "entropy": entropy,
            "q_mean": q_mean, "q_median": float(np.median(counts)), "universe_size": len(self.universe),
            "collision_proxy": proxy, "false_candidate_proxy": len(self.universe) * proxy,
            "ambiguity_mean": float(ambiguity.mean()), "ambiguity_median": float(np.median(ambiguity)),
        }
