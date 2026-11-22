import hmac
import json

import pandas as pd
import pytest

from experiments.rq1 import build_rq1_report, run_rq1
from src.common import paths
from src.common.config import load_config
from src.common.data.splitting import load_split, save_split, split_entities
from src.common.linking.bloom_blocked import BLOOM_BLOCKED, BloomBlockedLinker, blocking_token
from src.common.linking.threshold import select_single_tau
from src.common.seeding import make_rng


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    cfg = load_config("rq1")
    monkeypatch.setattr(paths, "app_dir", lambda: tmp_path)
    c = cfg.columns
    frame = pd.DataFrame([
        {c.record_id: f"R{entity}-{rep}", c.entity_id: f"E{entity}",
         c.description: f"Product {entity} 10 mg", c.dosage: "10 mg",
         c.dosage_form: "tablet", c.pack_size: "30"}
        for entity in range(8) for rep in range(2)
    ])
    monkeypatch.setattr(run_rq1, "load_noisy", lambda seed, level, cfg: frame.copy())
    path = paths.splits_dir(cfg, create=True) / "split_seed0.json"
    split = split_entities(frame[c.entity_id], cfg.val_fraction, make_rng(0, "split"))
    save_split(split, path)
    return cfg, frame, path


def test_blocking_token_uses_normalized_fields_and_key():
    key = b"phase7b-test"
    expected = hmac.digest(key, b"block:10mg|filmcoatedtablet|30", "sha256")
    assert blocking_token("10 MG", "Film-coated tablet", "30", key) == expected
    assert blocking_token("10mg", "film coated tablet", "30", key) == expected
    assert blocking_token("10mg", "film coated tablet", "30", b"other-key") != expected


def test_identical_description_links_only_within_same_block(dataset):
    cfg, frame, _ = dataset
    c = cfg.columns
    features = frame.head(3).drop(columns=c.entity_id).copy()
    features[c.description] = "Product 10 mg"
    features.loc[features.index[2], c.dosage] = "20 mg"
    linker = BloomBlockedLinker(0.90, cfg)
    prepared = linker.prepare(features, 0.60)
    assert list(zip(prepared.i, prepared.j)) == [(0, 1)]
    labels = linker.link(features)
    pd.testing.assert_series_equal(labels, prepared.labels_at(0.90))
    assert labels.iloc[0] == labels.iloc[1] != labels.iloc[2]


def test_posthoc_tuning_is_validation_only_and_p1_replays_default(dataset, tmp_path, monkeypatch):
    cfg, frame, split_file = dataset
    saved_split = load_split(split_file)
    original = split_file.read_bytes()
    ordinary = run_rq1.run_experiment(cfg, seeds=[0], out_dir=tmp_path / "ordinary")
    tune = run_rq1.tune_blocked_tau
    validation_entities = set(saved_split["validation"])
    calls = []

    def tune_validation_only(validation, grid, cfg):
        assert all(set(data[cfg.columns.entity_id]) == validation_entities for data in validation.values())
        table = tune(validation, grid, cfg)
        calls.append(table)
        return table

    monkeypatch.setattr(run_rq1, "tune_blocked_tau", tune_validation_only)
    first = run_rq1.run_experiment(cfg, seeds=[0], post_hoc="p1")
    runs = pd.read_csv(first / "raw_runs.csv").drop(columns="runtime_sec")
    ordinary_runs = pd.read_csv(ordinary / "raw_runs.csv").drop(columns="runtime_sec")
    pd.testing.assert_frame_equal(runs.loc[runs.method.ne(BLOOM_BLOCKED)].reset_index(drop=True), ordinary_runs)
    blocked = runs.loc[runs.method.eq(BLOOM_BLOCKED)]
    assert len(blocked) == 4 and blocked.field_set.eq("description").all()
    assert blocked.tau.eq(select_single_tau(calls[0])).all()

    c = cfg.columns
    frame.loc[frame[c.entity_id].isin(saved_split["test"]), c.description] = "Altered test description"
    run_rq1.run_experiment(cfg, seeds=[0], post_hoc="p1")
    pd.testing.assert_frame_equal(calls[0], calls[1])
    assert split_file.read_bytes() == original
    assert not (first / "splits").exists()


def test_p2_uses_separate_split_and_labeled_report(dataset):
    cfg, _, split_file = dataset
    original = split_file.read_bytes()
    out = run_rq1.run_experiment(cfg, seeds=[0], post_hoc="p2", val_fraction=0.50)
    assert split_file.read_bytes() == original
    new_split = load_split(out / "splits" / split_file.name)
    assert len(new_split["validation"]) == len(new_split["test"]) == 4
    assert set(load_split(split_file)["validation"]) < set(new_split["validation"])
    metadata = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["config"]["val_fraction"] == 0.50
    assert metadata["extra"]["blocking_fields"] == ["dosage", "dosage_form", "pack_size"]
    build_rq1_report.build_report(out / "raw_runs.csv", out / "tau_selection.csv", out)
    assert len(list((out / "figures").glob("*.png"))) == 2
    for table in (out / "tables").glob("*.md"):
        contents = table.read_text(encoding="utf-8")
        assert contents.startswith("## Post-hoc analysis")
        assert "Fuzzy match + exact dosage/pack blocking (post-hoc)" in contents


def test_posthoc_rejects_frozen_output_location(dataset):
    cfg, _, _ = dataset
    frozen = paths.results_dir(cfg, "rq1")
    with pytest.raises(ValueError, match="subdirectory of results/rq1_posthoc"):
        run_rq1.run_experiment(cfg, seeds=[0], post_hoc="p1", out_dir=frozen / "bad")
    assert not frozen.exists()
    out = run_rq1.run_experiment(cfg, seeds=[0], post_hoc="p1")
    with pytest.raises(ValueError, match="subdirectory of results/rq1_posthoc"):
        build_rq1_report.build_report(out / "raw_runs.csv", out / "tau_selection.csv", frozen)
    assert not frozen.exists()

    frozen.mkdir()
    for name in ("raw_runs.csv", "tau_selection.csv", "metadata.json", "h1_check.md"):
        (frozen / name).write_text("frozen", encoding="utf-8")
    with pytest.raises(ValueError, match="directory is frozen"):
        run_rq1.run_experiment(cfg, seeds=[0])
    with pytest.raises(ValueError, match="directory is frozen"):
        build_rq1_report.build_report(out / "raw_runs.csv", out / "tau_selection.csv", frozen / "smoke")
    assert {path.read_text(encoding="utf-8") for path in frozen.iterdir()} == {"frozen"}
