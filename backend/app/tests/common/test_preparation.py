from dataclasses import replace

import pandas as pd
import pytest

from src.common.config import load_config
from src.common.data.preparation import prepare_base_data, prepare_base_dataset
from src.common.seeding import make_rng

_RAW_COLUMNS = [
    "item description", "molecule/test type", "dosage", "dosage form", "unit of measure (per pack)"
]


def test_preserves_text_and_groups_by_the_canonical_tuple():
    cfg = load_config("rq1")
    raw = pd.DataFrame(
        [
            ("  Alpha, 10 MG!  ", "  CAFÉ /  X ", " 10 MG ", " Oral  Suspension  ", "030"),
            ("ALPHA [brand]", "café / x", "10 mg", "oral suspension", 30),
            ("Alpha different strength", "café / x", "20 mg", "oral suspension", 30),
            ("Alpha different punctuation", "café x", "10 mg", "oral suspension", 30),
            ("Kit no dosage", "Kit", None, "Test kit", 10),
            ("Kit blank dosage", "kit", "", "test kit", "010"),
            (None, "Kit", None, "Test kit", 10),
            ("   ", "Kit", None, "Test kit", 10),
            (None, None, None, None, None),
        ],
        columns=_RAW_COLUMNS,
    )
    result = prepare_base_data(raw, cfg)
    frame = result.records
    pd.testing.assert_frame_equal(prepare_base_dataset(raw, cfg), frame)
    assert result.empty_rows_removed == 3
    assert frame["raw_item_description"].tolist() == raw["item description"].iloc[:6].tolist()
    assert frame.loc[0, ["dosage", "dosage_form", "pack_size"]].tolist() == [
        " 10 MG ", " Oral  Suspension  ", "030"
    ]
    assert frame["record_id"].is_unique
    assert frame["record_id"].tolist() == [f"R{i:06d}" for i in range(1, 7)]
    ids = frame["entity_id"]
    assert ids[0] == ids[1]
    assert ids[4] == ids[5]
    assert len({ids[0], ids[2], ids[3], ids[4]}) == 4
    canonical = result.entity_map.set_index("entity_id").loc[ids[0]]
    assert canonical.tolist() == ["café / x", "10 mg", "oral suspension", "30", 2]
    assert result.entity_map.loc[result.entity_map["entity_id"] == ids[4], "dosage"].item() == ""


def test_reports_duplicates_without_dropping_them():
    cfg = load_config("rq1")
    raw = pd.DataFrame([("Alpha", "Alpha", "10mg", "Tablet", 30)] * 2, columns=_RAW_COLUMNS)
    result = prepare_base_data(raw, cfg)
    assert result.exact_duplicates == 1
    assert len(result.records) == 2
    assert result.entity_map["record_count"].tolist() == [2]


def test_cap_matches_the_fixed_rng_and_preserves_existing_record_ids():
    cfg = load_config("rq1")
    raw = pd.DataFrame(
        [(f"Alpha {i}", "Alpha", "10mg", "Tablet", 30) for i in range(27)]
        + [("Beta", "Beta", "10mg", "Tablet", 30)],
        columns=_RAW_COLUMNS,
    )
    raw["record_id"] = [f"source-{i}" for i in range(len(raw))]
    expected_positions = sorted(make_rng(0, "entity_cap").choice(range(27), size=20, replace=False))
    result = prepare_base_data(raw, cfg)
    assert (result.entities_capped, result.cap_rows_removed) == (1, 7)
    assert result.entity_map["record_count"].tolist() == [20, 1]
    assert result.records["record_id"].tolist() == raw["record_id"].iloc[expected_positions + [27]].tolist()
    pd.testing.assert_frame_equal(result.records, prepare_base_dataset(raw, cfg))


def test_sample_is_deterministic_and_retains_whole_entities_with_stable_ids():
    cfg = load_config("rq1")
    raw = pd.DataFrame(
        [(label, label, "10mg", "Tablet", 30) for label in ("A", "B", "C", "D") for _ in range(3)],
        columns=_RAW_COLUMNS,
    )
    full = prepare_base_dataset(raw, cfg)
    sample_cfg = replace(cfg, sample_entities=2)
    sample = prepare_base_data(raw, sample_cfg)
    assert len(sample.entity_map) == 2
    assert sample.sample_rows_removed == 6
    assert sample.entity_map["record_count"].tolist() == [3, 3]
    pd.testing.assert_frame_equal(sample.records, prepare_base_dataset(raw, sample_cfg))
    pd.testing.assert_frame_equal(
        sample.records,
        full.loc[full["entity_id"].isin(sample.entity_map["entity_id"])].reset_index(drop=True),
    )


def test_malformed_pack_size_is_rejected():
    raw = pd.DataFrame([("Alpha", "Alpha", "10mg", "Tablet", "30.5")], columns=_RAW_COLUMNS)
    with pytest.raises(ValueError, match="Pack size must be an integer"):
        prepare_base_dataset(raw, load_config("rq1"))
