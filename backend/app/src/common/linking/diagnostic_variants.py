"""Opt-in linkage alternatives for the fixed diagnostics."""

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from src.common.config import Config, unit_interval
from src.common.linking.bloom import BloomLinker
from src.common.linking.exact import keyed_sha256
from src.common.preprocessing.normalizer import normalize_series
from src.common.similarity.dice import dice_matrix


class DosageBlockedBloomLinker(BloomLinker):
    """Link description filters only within identical normalized dosage tokens."""

    def __init__(self, cfg: Config):
        super().__init__("V2", "description", cfg.tau_grid.start, cfg)
        self._dosage = cfg.columns.dosage
        self._key = bytes.fromhex(cfg.bloom.hmac_key)

    def prepare(self, df: pd.DataFrame, tau_min: float):
        prepared = super().prepare(df, tau_min)
        doses = normalize_series(df[self._dosage])
        tokens = doses.map(lambda dosage: keyed_sha256(dosage, self._key)).to_numpy()
        same_dosage = tokens[prepared.i] == tokens[prepared.j]
        return replace(
            prepared, i=prepared.i[same_dosage], j=prepared.j[same_dosage], sim=prepared.sim[same_dosage],
        )


@dataclass(frozen=True)
class PreparedStar:
    record_ids: pd.Index
    scores: np.ndarray
    tau_min: float

    def labels_at(self, tau: float) -> pd.Series:
        tau = unit_interval(tau, "tau")
        if tau < self.tau_min:
            raise ValueError("tau must be at least the prepared tau_min")
        labels = np.empty(len(self.record_ids), dtype=np.intp)
        leaders = []
        for index in range(len(labels)):
            scores = self.scores[index, leaders]
            if leaders:
                best = int(scores.argmax())
                if scores[best] >= tau:
                    labels[index] = best
                    continue
            labels[index] = len(leaders)
            leaders.append(index)
        return pd.Series(labels, index=self.record_ids)


class StarBloomLinker(BloomLinker):
    """Assign to the closest eligible fixed leader in the input order."""

    def __init__(self, cfg: Config):
        super().__init__("V3", "composite", cfg.tau_grid.start, cfg)

    def prepare(self, df: pd.DataFrame, tau_min: float):
        record_ids, bits = self.encode_records(df)
        return PreparedStar(record_ids, dice_matrix(bits, bits), unit_interval(tau_min, "tau_min"))
