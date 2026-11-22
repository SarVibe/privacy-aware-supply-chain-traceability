import pandas as pd
import pytest
from pandas.api.types import is_integer_dtype

from src.common.config import load_config
from src.common.linking import bloom
from src.common.linking.base import Linker
from src.common.linking.bloom import BloomLinker


@pytest.fixture
def features():
    return pd.DataFrame(
        {
            "record_id": ["r4", "r2", "r5", "r1"],
            "raw_item_description": [
                "Paracetamol 500mg", "Paracetmol 500mg", "Paracetamool 500mg", "Zidovudine 100mg"
            ],
        },
        index=[8, 3, 4, 0],
    )


def test_loose_and_strict_thresholds_on_spelling_variants(features):
    cfg = load_config("rq1")
    linker: Linker = BloomLinker("bloom_fuzzy", "description", 0.7, cfg)
    labels = linker.link(features)
    assert linker.name == "bloom_fuzzy"
    assert labels.iloc[0] == labels.iloc[1] == labels.iloc[2] != labels.iloc[3]
    assert labels.index.equals(pd.Index(features["record_id"]))
    assert is_integer_dtype(labels)
    strict = BloomLinker("bloom_fuzzy", "description", 0.99, cfg).link(features)
    assert strict.nunique() == 4


def test_prepare_reuses_scores_and_agrees_with_link(features, monkeypatch):
    linker = BloomLinker("bloom_fuzzy", "description", 0.7, load_config("rq1"))
    pd.testing.assert_series_equal(linker.link(features), linker.prepare(features, 0.7).labels_at(0.7))
    prepared = linker.prepare(features, 0.0)

    def unexpected_compute(*args, **kwargs):
        pytest.fail("labels_at tried to recompute scores")

    monkeypatch.setattr(bloom, "compute_similar_pairs", unexpected_compute)
    scores = {(i, j): score for i, j, score in zip(prepared.i, prepared.j, prepared.sim)}
    assert scores[(0, 3)] < scores[(0, 1)] < 1.0
    assert prepared.labels_at(0.7).nunique() == 2
    assert prepared.labels_at(0.99).nunique() == 4


def test_prepared_scores_reject_threshold_below_cached_minimum(features):
    linker = BloomLinker("bloom_fuzzy", "description", 0.7, load_config("rq1"))
    with pytest.raises(ValueError, match="tau_min"):
        linker.prepare(features, 0.7).labels_at(0.6)
