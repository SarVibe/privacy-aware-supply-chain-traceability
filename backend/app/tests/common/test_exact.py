import hashlib

import pandas as pd
from pandas.api.types import is_integer_dtype

from src.common.config import load_config
from src.common.linking.base import Linker
from src.common.linking.exact import NORMALIZED_EXACT, RAW_EXACT, ExactLinker, sha256_hex


def test_hash_matches_known_sha256_and_uses_utf8():
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert sha256_hex("abc") == expected == hashlib.sha256(b"abc").hexdigest()
    assert sha256_hex(" café ") == hashlib.sha256(" café ".encode("utf-8")).hexdigest()


def test_raw_and_normalized_exact_cluster_without_truth_labels():
    cfg = load_config("rq1")
    df = pd.DataFrame(
        {
            cfg.columns.record_id: ["r5", "r1", "r2", "r3", "r4"],
            cfg.columns.description: ["Pill-10mg", "Pill-10mg", "pill-10mg", "Pill_10mg", "Pill-10ng"],
        },
        index=[10, 3, 1, 6, 7],
    )
    raw: Linker = ExactLinker(RAW_EXACT, "description", False, cfg)
    normalized: Linker = ExactLinker(NORMALIZED_EXACT, "description", True, cfg)
    raw_labels, normalized_labels = raw.link(df), normalized.link(df)
    assert raw.name == "raw_exact"
    assert normalized.name == "normalized_exact"
    assert raw_labels.tolist() == [0, 0, 1, 2, 3]
    assert normalized_labels.tolist() == [0, 0, 0, 0, 1]
    assert raw_labels.index.equals(pd.Index(df[cfg.columns.record_id]))
    assert is_integer_dtype(raw_labels) and is_integer_dtype(normalized_labels)
    pd.testing.assert_series_equal(raw.link(df), raw_labels)
    pd.testing.assert_series_equal(normalized.link(df), normalized_labels)


def test_composite_exact_respects_field_boundaries():
    cfg = load_config("rq1")
    df = pd.DataFrame(
        {
            cfg.columns.record_id: ["r1", "r2", "r3"],
            cfg.columns.description: ["Ab", "A", "ab"],
            cfg.columns.dosage: ["C", "BC", "c"],
            cfg.columns.dosage_form: [None, None, ""],
            cfg.columns.pack_size: [30, 30, 30],
        }
    )
    linker = ExactLinker(NORMALIZED_EXACT, "composite", True, cfg)
    assert linker.link(df).tolist() == [0, 1, 0]
