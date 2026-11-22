"""Dice similarity for binary uint8 filters and their unordered pairs."""

import numpy as np
from numpy.typing import NDArray


def _dice_block(
    left: NDArray[np.float32],
    right: NDArray[np.float32],
    left_sizes: NDArray[np.float64],
    right_sizes: NDArray[np.float64],
) -> NDArray[np.float64]:
    scores = (left @ right.T).astype(np.float64)
    scores *= 2.0
    denominator = left_sizes[:, None] + right_sizes[None, :]
    # Both the overlap and the denominator are zero for two empty filters.
    return np.divide(scores, denominator, out=scores, where=denominator > 0)


def dice_matrix(A: NDArray[np.uint8], B: NDArray[np.uint8]) -> NDArray[np.float64]:
    """Return Dice scores for rows of two bit matrices with equal widths."""
    if A.ndim != 2 or B.ndim != 2 or A.shape[1] != B.shape[1]:
        raise ValueError("Dice requires two bit matrices with the same width")
    left, right = A.astype(np.float32), B.astype(np.float32)
    return _dice_block(left, right, left.sum(axis=1, dtype=np.float64), right.sum(axis=1, dtype=np.float64))


def dice_pair(a: NDArray[np.uint8], b: NDArray[np.uint8]) -> float:
    """Return Dice similarity for two one-dimensional filters."""
    return float(dice_matrix(a[None, :], b[None, :])[0, 0])


def compute_similar_pairs(
    bits: NDArray[np.uint8], tau_min: float, block_size: int = 1000
) -> tuple[NDArray[np.intp], NDArray[np.intp], NDArray[np.float64]]:
    """Return i < j pairs meeting tau_min, in block traversal order."""
    if bits.ndim != 2:
        raise ValueError("bits must be a two-dimensional matrix")
    if not 0 <= tau_min <= 1:
        raise ValueError("tau_min must be in [0, 1]")
    if type(block_size) is not int or block_size < 1:
        raise ValueError("block_size must be a positive integer")
    n_records = len(bits)
    starts, ends, similarities = [], [], []
    if n_records >= 2:
        # Use at least two blocks, including when all rows fit in block_size.
        size = min(block_size, (n_records + 1) // 2)
        floats = bits.astype(np.float32)
        row_sizes = floats.sum(axis=1, dtype=np.float64)
        for start in range(0, n_records, size):
            left = slice(start, start + size)
            for end in range(start, n_records, size):
                right = slice(end, end + size)
                scores = _dice_block(floats[left], floats[right], row_sizes[left], row_sizes[right])
                keep = scores >= tau_min
                if start == end:
                    keep = np.triu(keep, k=1)
                i, j = np.nonzero(keep)
                if i.size:
                    starts.append(i + start)
                    ends.append(j + end)
                    similarities.append(scores[i, j])
    if not starts:
        return np.empty(0, dtype=np.intp), np.empty(0, dtype=np.intp), np.empty(0, dtype=np.float64)
    return np.concatenate(starts), np.concatenate(ends), np.concatenate(similarities)
