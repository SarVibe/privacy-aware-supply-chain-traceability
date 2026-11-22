"""Threshold similarity pairs and return connected-component labels."""

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components


def labels_from_pairs(
    n: int, i: NDArray[np.integer], j: NDArray[np.integer], sim: NDArray[np.floating], tau: float
) -> NDArray[np.signedinteger]:
    """Group records connected by an undirected path of edges at or above tau."""
    if not 0 <= tau <= 1:
        raise ValueError("tau must be in [0, 1]")
    keep = sim >= tau
    graph = csr_matrix((np.ones(np.count_nonzero(keep), dtype=np.uint8), (i[keep], j[keep])), shape=(n, n))
    _, labels = connected_components(graph, directed=False)
    return labels
