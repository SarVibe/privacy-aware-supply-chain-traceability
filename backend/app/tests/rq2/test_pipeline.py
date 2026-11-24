import math
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from src.rq2.privacy_pipeline import build_scenario, run_bloom, run_exact
from src.rq2.results_schema import validate_results
from src.rq2.rq2_dataset import apply_real_frequency_counts, csv_dataset, load_research_dataset, synthetic_dataset


def scenario_at(config, noise):
    seed = config.seeds[0]
    ds = load_research_dataset(config, seed, noise)
    return ds, build_scenario(ds, seed, noise, n_records=100)


def test_scenarios_use_pregenerated_records_and_the_final_rq1_split(golden_config):
    ds, a = scenario_at(golden_config, 0.15)
    b = build_scenario(ds, a.seed, a.noise, n_records=100)
    assert a.b_norm == b.b_norm == ds.noisy_norm
    np.testing.assert_array_equal(a.test_idx, b.test_idx)
    np.testing.assert_array_equal(a.victim_ids, b.victim_ids)
    assert a.key == b.key == bytes.fromhex(golden_config.bloom.hmac_key)
    assert {ds.entity_ids[i] for i in a.test_idx} == set(ds.linkage.test[golden_config.columns.entity_id])
    assert all(value in ds.noisy_records_by_entity[int(i)] for i, value in zip(a.victim_ids, a.victim_norm))
    with pytest.raises(ValueError, match="pre-generated"):
        build_scenario(synthetic_dataset(10), a.seed, a.noise, n_records=20)
    with pytest.raises(ValueError, match="seed and noise level"):
        build_scenario(ds, a.seed + 1, a.noise, n_records=20)


def test_rows_report_primary_and_secondary_metrics(golden_config):
    ds, scenario = scenario_at(golden_config, 0.05)
    rows = [run_exact(ds, scenario), run_bloom(ds, scenario, 1024, 4)]
    validate_results(pd.DataFrame(rows))
    for row in rows:
        assert row["n_records"] == len(ds.linkage.test)
        for metric in ("f1", "precision", "recall", "reid_top1", "freq_success", "cross_party_f1",
                       "cross_party_precision", "cross_party_recall", "cross_party_fpr"):
            assert 0 <= row[metric] <= 1
    assert "eps" not in rows[1] and "flip_p" not in rows[1]
    assert rows[1]["cross_party_tau"] == rows[1]["tau_unc"]


def test_no_noise_preserves_secondary_exact_pairs(golden_config):
    ds, scenario = scenario_at(golden_config, 0)
    assert run_exact(ds, scenario)["cross_party_recall"] == 1
    assert run_bloom(ds, scenario, 1024, 4)["cross_party_recall"] == 1


def test_no_matching_dictionary_tokens(golden_config):
    ds, scenario = scenario_at(golden_config, 0.15)
    scenario = replace(scenario, b_norm=[f"unmatched victim {i}" for i in range(ds.n)])
    row = run_exact(ds, scenario)
    assert row["reid_top1"] == row["reid_top5"] == 0
    for column in ("reid_ties", "reid_cands_delta", "reid_ties_count",
                   "reid_cands_delta_count", "reid_top1_conditional"):
        assert math.isnan(row[column])
    validate_results(pd.DataFrame([row]))


def test_collision_tuning_changes_fill_and_load(golden_config):
    ds, scenario = scenario_at(golden_config, 0.15)
    standard = run_bloom(ds, scenario, 1024, 4)
    for length, hashes in [(512, 10), (256, 30), (128, 50)]:
        tight = run_bloom(ds, scenario, length, hashes)
        assert tight["fill"] > standard["fill"] and tight["load"] > standard["load"]
        assert tight["degenerate"] in (0, 1)
        assert 0 <= tight["f1"] <= 1
        assert 0 <= tight["cross_party_f1"] <= 1


def test_research_dataset_limit_preserves_record_order(golden_config):
    cfg = golden_config
    full = load_research_dataset(cfg, cfg.seeds[0], 0.05)
    bounded = load_research_dataset(cfg, cfg.seeds[0], 0.05, max_records=100)
    rid = cfg.columns.record_id
    assert len(bounded.linkage.validation) + len(bounded.linkage.test) <= 100
    kept = set(bounded.linkage.test[rid])
    assert bounded.linkage.test[rid].tolist() == full.linkage.test.loc[full.linkage.test[rid].isin(kept), rid].tolist()


def test_real_frequency_weights_join_normalized_descriptions(tmp_path):
    master = tmp_path / "master.csv"
    shipments = tmp_path / "shipments.csv"
    master.write_text("raw_item_description\nAlpha pack\nBeta pack\n")
    shipments.write_text("item description\nALPHA PACK\nAlpha  Pack\nalpha pack\nOther item\n")
    ds = apply_real_frequency_counts(csv_dataset(master, "raw_item_description"), shipments)
    np.testing.assert_array_equal(ds.counts, [3, 1])
    np.testing.assert_allclose(ds.weights, [0.75, 0.25])
