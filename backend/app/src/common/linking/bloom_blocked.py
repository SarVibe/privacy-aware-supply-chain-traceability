"""Post-hoc Bloom matching within exact dosage, form and pack-size blocks."""

import hmac
from collections import defaultdict

import numpy as np
import pandas as pd

from src.common.config import Config
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.linking.bloom import PreparedBloom
from src.common.preprocessing.field_builder import build_field_strings
from src.common.preprocessing.normalizer import normalize
from src.common.similarity.dice import compute_similar_pairs

BLOOM_BLOCKED = "bloom_blocked"
DESCRIPTION = "description"


def blocking_fields(cfg: Config) -> tuple[str, str, str]:
    """Return the configured columns in blocking-token order."""
    return cfg.columns.dosage, cfg.columns.dosage_form, cfg.columns.pack_size


def blocking_token(dosage: object, form: object, pack: object, key: bytes) -> bytes:
    """Hash the normalized structured fields in a separate HMAC namespace."""
    fields = "|".join(normalize(value) for value in (dosage, form, pack))
    return hmac.digest(key, f"block:{fields}".encode("utf-8"), "sha256")


class BloomBlockedLinker:
    """Compare normalized descriptions only inside each structured-field block."""

    name = BLOOM_BLOCKED

    def __init__(self, tau: float, cfg: Config) -> None:
        self.tau = tau
        self._cfg = cfg
        bloom = cfg.bloom
        self._key = bytes.fromhex(bloom.hmac_key)
        self._encoder = BloomFilterEncoder(bloom.l, bloom.k, bloom.q, self._key, bloom.pad_char)

    def prepare(self, df: pd.DataFrame, tau_min: float) -> PreparedBloom:
        """Cache the within-block pairs eligible for thresholds at or above tau_min."""
        descriptions = build_field_strings(df, DESCRIPTION, self._cfg, normalize=True)
        blocks = defaultdict(list)
        fields = df.loc[:, list(blocking_fields(self._cfg))]
        for pos, (dosage, form, pack) in enumerate(fields.itertuples(index=False, name=None)):
            blocks[blocking_token(dosage, form, pack, self._key)].append(pos)

        left, right, similarities = [], [], []
        for positions in blocks.values():
            if len(positions) < 2:
                continue
            indices = np.asarray(positions, dtype=np.intp)
            bits = self._encoder.encode_many(descriptions.iloc[indices])
            i, j, sim = compute_similar_pairs(bits, tau_min)
            left.append(indices[i])
            right.append(indices[j])
            similarities.append(sim)
        return PreparedBloom(
            descriptions.index,
            np.concatenate(left) if left else np.empty(0, dtype=np.intp),
            np.concatenate(right) if right else np.empty(0, dtype=np.intp),
            np.concatenate(similarities) if similarities else np.empty(0, dtype=np.float64),
            tau_min,
        )

    def link(self, df: pd.DataFrame) -> pd.Series:
        """Return connected-component labels at the configured cutoff."""
        return self.prepare(df, self.tau).labels_at(self.tau)
