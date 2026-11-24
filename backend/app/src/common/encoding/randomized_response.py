"""Independent randomized-response bit flips for the NumPy experiment encoder."""

from functools import partial

import numpy as np
from scipy.special import expit

from src.common.config import positive_integer, validate_epsilon
from src.common.encoding.bloom_filter import PostTransform
from src.common.seeding import make_rng


def flip_probability(eps: float, k: int) -> float:
    eps = validate_epsilon(eps)
    return float(expit(-(eps / positive_integer(k, "k"))))


def randomized_response(bf: np.ndarray, eps: float, k: int, rng: np.random.Generator) -> np.ndarray:
    p = flip_probability(eps, k)
    if p == 0:
        return bf.copy()
    flips = rng.random(bf.shape) < p
    return (bf ^ flips.astype(np.uint8)).astype(np.uint8)


def response_transform(seed: int, l: int, k: int, eps: float) -> PostTransform | None:
    """Build a reproducible per-record transform, or omit it for zero flip probability."""
    if flip_probability(eps, k) == 0:
        return None
    rng = make_rng(seed, f"response:record:{l}:{k}:{float(eps)}")
    return partial(randomized_response, eps=eps, k=k, rng=rng)
