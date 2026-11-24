"""RQ2 structural, linkage, and noise metrics."""
import math

import numpy as np

from src.common.encoding.bloom_filter import fill_ratio
from src.common.noise_injection import levenshtein

def fill_stats(bf: np.ndarray):
    fill = fill_ratio(bf)
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
    """Compare aligned, already normalized field strings."""
    unchanged = sum(a == b for a, b in zip(originals, noisy, strict=True))
    distances = [levenshtein(a, b) for a, b in zip(originals, noisy, strict=True)]
    n = len(originals)
    return {
        "unchanged_fraction": unchanged / n if n else 0.0,
        "average_normalized_edit_distance": sum(distances) / n if n else 0.0,
    }
