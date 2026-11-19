"""RQ2 structural, linkage, and noise metrics."""
import math

import numpy as np

from src.common.noise_injection import levenshtein
from src.rq2.text_normalizer import normalize

def fill_stats(bf: np.ndarray):
    fill = bf.mean(axis=1)
    return float(fill.mean()), float(fill.std())


def bit_entropy(bf: np.ndarray) -> float:
    p = bf.mean(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        h = -(p * np.log2(p) + (1 - p) * np.log2(1 - p))
    return float(np.nan_to_num(h, nan=0.0).mean())


def collision_load(mean_distinct_qgrams: float, k: int, l: int) -> float:
    return mean_distinct_qgrams * k / l


def expected_fill(load: float) -> float:
    return 1.0 - math.exp(-load)


def effective_noise(originals: list, noisy: list) -> dict:
    normalized_original = [normalize(str(s)) for s in originals]
    normalized_noisy = [normalize(str(s)) for s in noisy]
    unchanged = sum(a == b for a, b in zip(normalized_original, normalized_noisy))
    distances = [levenshtein(a, b) for a, b in zip(normalized_original, normalized_noisy)]
    n = len(normalized_original)
    return {
        "unchanged_fraction": unchanged / n if n else 0.0,
        "average_normalized_edit_distance": sum(distances) / n if n else 0.0,
    }
