from dataclasses import replace

import pandas as pd
import pytest

from src.common.config import load_config
from src.common.data.splitting import apply_split, load_split, save_split, split_entities
from src.common.seeding import make_rng


def test_entity_splits_are_disjoint_complete_and_keep_whole_entities():
    ids = [f"E{i:04d}" for i in range(20)]
    frame = pd.DataFrame({"entity_id": ids * 3, "record_id": range(60)})
    split = split_entities(frame["entity_id"], 0.30, make_rng(0, "split"))
    validation, test = apply_split(frame, split)
    validation_ids, test_ids = set(validation["entity_id"]), set(test["entity_id"])
    assert len(validation_ids) == 6
    assert len(test_ids) == 14
    assert validation_ids.isdisjoint(test_ids)
    assert validation_ids | test_ids == set(ids)
    assert all(validation["entity_id"].value_counts() == 3)
    assert all(test["entity_id"].value_counts() == 3)


def test_seed_and_distinct_entity_set_determine_split():
    ids = [f"E{i:04d}" for i in range(30)]
    first = split_entities(ids, 0.30, make_rng(0, "split"))
    assert first == split_entities(ids[::-1] * 2, 0.30, make_rng(0, "split"))
    assert set(first["validation"]) != set(split_entities(ids, 0.30, make_rng(1, "split"))["validation"])


def test_split_json_round_trip(tmp_path):
    split = {"validation": ["E0001"], "test": ["E0002", "E0003"]}
    path = tmp_path / "split_seed0.json"
    save_split(split, path)
    assert load_split(path) == split


def test_split_accepts_a_configured_entity_column_and_requires_coverage():
    cfg = load_config("rq1")
    cfg = replace(cfg, columns=replace(cfg.columns, entity_id="truth"))
    frame = pd.DataFrame({"truth": ["E0001", "E0002"]})
    split = {"validation": ["E0001"], "test": ["E0002"]}
    validation, test = apply_split(frame, split, cfg)
    assert validation["truth"].tolist() == ["E0001"]
    assert test["truth"].tolist() == ["E0002"]
    with pytest.raises(ValueError, match="exactly cover"):
        apply_split(frame, {"validation": ["E0001"], "test": []}, cfg)


def test_tiny_splits_keep_both_sides_when_possible():
    assert split_entities(["E0001"], 0.30, make_rng(0, "split")) == {
        "validation": [], "test": ["E0001"]
    }
    split = split_entities(["E0001", "E0002"], 0.01, make_rng(0, "split"))
    assert len(split["validation"]) == len(split["test"]) == 1
