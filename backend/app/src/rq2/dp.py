"""Randomized-response bit flipping (the C1 differential-privacy mechanism).

Each bit is flipped independently with p = 1 / (1 + e^(eps / delta)), delta = k
(adding/removing one q-gram changes at most k bits), so each bit is (eps/k)-RR
and the whole filter is eps-DP at q-gram level. Noise is drawn once per stored
record: identical entities in different records get *different* noise.
"""
import math

import numpy as np


def flip_probability(eps: float, k: int) -> float:
    if math.isinf(eps):
        return 0.0
    return 1.0 / (1.0 + math.exp(eps / k))


def randomized_response(bf: np.ndarray, eps: float, k: int, rng: np.random.Generator) -> np.ndarray:
    p = flip_probability(eps, k)
    if p == 0.0:
        return bf.copy()
    flips = rng.random(bf.shape) < p
    return (bf ^ flips.astype(np.uint8)).astype(np.uint8)
