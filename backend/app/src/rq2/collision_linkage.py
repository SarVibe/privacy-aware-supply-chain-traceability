"""Record encoding and cached RQ1-compatible linkage for the collision study."""

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from src.common.config import Config
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.evaluation.metrics import evaluate_clusters
from src.common.linking.bloom import PreparedBloom
from src.common.preprocessing.field_builder import build_field_strings
from src.common.similarity.dice import compute_similar_pairs


def build_collision_encoder(cfg: Config) -> BloomFilterEncoder:
    settings = cfg.bloom
    return BloomFilterEncoder(
        settings.l, settings.k, settings.q, bytes.fromhex(settings.hmac_key), settings.pad_char
    )


def cohort_tokens(frame: pd.DataFrame, cfg: Config, field_set: str, encoder: BloomFilterEncoder) -> list[set[str]]:
    strings = build_field_strings(frame, field_set, cfg, normalize=True)
    return [encoder.grams(text) for text in strings]


def prepare_collision_scores(
    frame: pd.DataFrame, bits: NDArray[np.uint8], cfg: Config
) -> PreparedBloom:
    """Keep every unordered Dice pair for clustering and separation metrics."""
    ids = pd.Index(frame[cfg.columns.record_id])
    if len(bits) != len(ids):
        raise ValueError("The filter matrix must align with the record frame")
    return PreparedBloom(ids, *compute_similar_pairs(bits, 0.0), 0.0)


def score_collision_clusters(frame: pd.DataFrame, prepared: PreparedBloom, tau: float, cfg: Config) -> dict:
    truth = frame.set_index(cfg.columns.record_id)[cfg.columns.entity_id]
    return evaluate_clusters(truth, prepared.labels_at(tau))
