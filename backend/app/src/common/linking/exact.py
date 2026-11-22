"""SHA-256 exact linking over raw or normalized field strings."""

from hashlib import sha256

import pandas as pd

from src.common.config import Config
from src.common.preprocessing.field_builder import build_field_strings

RAW_EXACT = "raw_exact"
NORMALIZED_EXACT = "normalized_exact"


def sha256_hex(text: str) -> str:
    """Hash the UTF-8 encoding of a field string as a SHA-256 hex digest."""
    return sha256(text.encode("utf-8")).hexdigest()


class ExactLinker:
    """Group records with equal SHA-256 digests."""

    def __init__(self, name: str, field_set: str, normalize: bool, cfg: Config) -> None:
        self.name = name
        self.field_set = field_set
        self.normalize = normalize
        self.cfg = cfg

    def link(self, df: pd.DataFrame) -> pd.Series:
        """Return an integer label for each record, indexed by record ID."""
        strings = build_field_strings(df, self.field_set, self.cfg, self.normalize)
        labels, _ = pd.factorize(strings.map(sha256_hex), sort=False)
        return pd.Series(labels, index=strings.index)
