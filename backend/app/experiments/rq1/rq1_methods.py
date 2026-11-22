"""Construct the RQ1 linking methods."""

from src.common.config import Config
from src.common.linking.bloom import BloomLinker
from src.common.linking.exact import NORMALIZED_EXACT, RAW_EXACT, ExactLinker


def build_exact_linkers(cfg: Config, field_set: str) -> tuple[ExactLinker, ExactLinker]:
    """Return the raw and normalized SHA-256 baselines in that order."""
    return (
        ExactLinker(RAW_EXACT, field_set, False, cfg),
        ExactLinker(NORMALIZED_EXACT, field_set, True, cfg),
    )


def build_bloom_linker(cfg: Config, field_set: str, tau: float) -> BloomLinker:
    """Return the keyed Bloom fuzzy linker for the requested cutoff."""
    return BloomLinker("bloom_fuzzy", field_set, tau, cfg)
