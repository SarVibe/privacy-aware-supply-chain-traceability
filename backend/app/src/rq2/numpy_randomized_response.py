import math

import numpy as np
from scipy.special import expit

from .parameter_validation import validate_eps


def flip_probability(eps: float, k: int) -> float:
    eps = validate_eps(eps)
    if k <= 0:
        raise ValueError("k must be >= 1")
    if eps < 0:
        raise ValueError("eps must be >= 0")
    if math.isinf(eps):
        return 0.0
    return float(expit(-(eps / k)))


def randomized_response(bf: np.ndarray, eps: float, k: int, rng: np.random.Generator) -> np.ndarray:
    p = flip_probability(eps, k)
    if p == 0.0:
        return bf.copy()
    flips = rng.random(bf.shape) < p
    return (bf ^ flips.astype(np.uint8)).astype(np.uint8)
