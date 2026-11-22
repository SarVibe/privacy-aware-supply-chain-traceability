import pandas as pd
import pytest

from experiments.rq1.rq1_methods import build_bloom_linker, build_exact_linkers
from src.common.config import load_config


@pytest.mark.parametrize("field_set,n_expected", [("description", 1), ("composite", 2)])
def test_factory_names_field_sets_and_tau(field_set, n_expected):
    cfg = load_config("rq1")
    frame = pd.DataFrame({
        "record_id": ["r1", "r2"],
        "raw_item_description": ["Alpha", "Alpha"],
        "dosage": ["10mg", "20mg"],
        "dosage_form": ["Tablet", "Tablet"],
        "pack_size": ["20", "20"],
    })
    raw, normalized = build_exact_linkers(cfg, field_set)
    assert (raw.name, normalized.name) == ("raw_exact", "normalized_exact")
    assert raw.normalize is False and normalized.normalize is True
    assert raw.link(frame).nunique() == normalized.link(frame).nunique() == n_expected
    fuzzy = build_bloom_linker(cfg, field_set, 0.99)
    assert fuzzy.name == "bloom_fuzzy" and fuzzy.tau == 0.99
    assert fuzzy.link(frame).nunique() == n_expected
