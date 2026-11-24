"""SHA-256 exact linking over raw or normalized field strings."""

import hmac
from hashlib import sha256

import pandas as pd

from src.common.config import Config
from src.common.preprocessing.field_builder import build_field_strings

RAW_EXACT = "raw_exact"
NORMALIZED_EXACT = "normalized_exact"


def sha256_hex(text: str) -> str:
    """Hash the UTF-8 encoding of a field string as a SHA-256 hex digest."""
    return sha256(text.encode("utf-8")).hexdigest()


def keyed_sha256(text: str, key: bytes) -> bytes:
    """Return the HMAC-SHA256 token of a field string."""
    return hmac.digest(key, text.encode("utf-8"), "sha256")


class ExactLinker:
    """Group records with equal SHA-256 digests."""

    def __init__(self, name: str, field_set: str, normalize: bool, cfg: Config, *, key: bytes | None = None) -> None:
        self.name = name
        self.field_set = field_set
        self.normalize = normalize
        self.cfg = cfg
        self._key = key

    def link(self, df: pd.DataFrame) -> pd.Series:
        """Return an integer label for each record, indexed by record ID."""
        strings = build_field_strings(df, self.field_set, self.cfg, self.normalize)
        if self._key is None:
            tokens = strings.map(sha256_hex)
        else:
            tokens = strings.map(lambda text: keyed_sha256(text, self._key))
        labels, _ = pd.factorize(tokens, sort=False)
        return pd.Series(labels, index=strings.index)
