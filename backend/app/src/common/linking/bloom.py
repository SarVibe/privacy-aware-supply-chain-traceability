"""Link normalized records by keyed Bloom filter Dice similarity."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from src.common.config import Config
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.linking.clustering import labels_from_pairs
from src.common.preprocessing.field_builder import build_field_strings
from src.common.similarity.dice import compute_similar_pairs


@dataclass(frozen=True)
class PreparedBloom:
    """Retain the pairs that can contribute to thresholds at or above tau_min."""

    record_ids: pd.Index
    i: NDArray[np.intp]
    j: NDArray[np.intp]
    sim: NDArray[np.float64]
    tau_min: float

    def labels_at(self, tau: float) -> pd.Series:
        """Return integer cluster labels at a threshold covered by these pairs."""
        if tau < self.tau_min:
            raise ValueError("tau must be at least the prepared tau_min")
        labels = labels_from_pairs(len(self.record_ids), self.i, self.j, self.sim, tau)
        return pd.Series(labels, index=self.record_ids)


class BloomLinker:
    """Cluster records through thresholded, undirected Dice edges."""

    def __init__(self, name: str, field_set: str, tau: float, cfg: Config) -> None:
        self.name = name
        self._field_set = field_set
        self.tau = tau
        self._cfg = cfg
        bloom = cfg.bloom
        self._encoder = BloomFilterEncoder(bloom.l, bloom.k, bloom.q, bytes.fromhex(bloom.hmac_key), bloom.pad_char)

    def encode_records(self, df: pd.DataFrame) -> tuple[pd.Index, NDArray[np.uint8]]:
        """Encode records in the order of their stable record IDs in the input."""
        strings = build_field_strings(df, self._field_set, self._cfg, normalize=True)
        return strings.index, self._encoder.encode_many(strings)

    def prepare(self, df: pd.DataFrame, tau_min: float) -> PreparedBloom:
        """Encode record fields and compute reusable unordered similarity pairs."""
        record_ids, bits = self.encode_records(df)
        i, j, sim = compute_similar_pairs(bits, tau_min)
        return PreparedBloom(record_ids, i, j, sim, tau_min)

    def link(self, df: pd.DataFrame) -> pd.Series:
        """Return integer cluster labels for the configured threshold."""
        return self.prepare(df, self.tau).labels_at(self.tau)
