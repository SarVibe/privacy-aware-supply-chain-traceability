import math
from dataclasses import replace

import numpy as np
import pandas as pd

from src.rq2.rq2_dataset import apply_real_frequency_counts, csv_dataset, synthetic_dataset
from src.rq2.privacy_pipeline import build_scenario, run_bloom, run_exact
from src.rq2.rq2_dataset import controlled_noise_dataset
from src.rq2.results_schema import validate_results
from src.application_config import Config

REQUIRED = {"method", "l", "k", "noise", "seed", "f1", "precision", "recall", "auc", "reid_top1", "reid_top5",
            "reid_cands_delta", "freq_success", "bit_success", "fill", "entropy", "load", "tau",
            "f1_unc", "precision_unc", "recall_unc", "fpr_unc", "tau_unc",
            "feasible_01", "f1_01", "tau_01", "fpr_01",
            "feasible_05", "f1_05", "tau_05", "fpr_05", "degenerate"}


def test_scenarios_are_reproducible_and_paired():
    ds = synthetic_dataset(120, seed=0)
    a = build_scenario(ds, seed=1, noise=0.15, n_records=400)
    b = build_scenario(ds, seed=1, noise=0.15, n_records=400)
    c = build_scenario(ds, seed=2, noise=0.15, n_records=400)
    assert a.b_norm == b.b_norm and (a.test_idx == b.test_idx).all() and a.key == b.key
    assert a.b_norm != c.b_norm


def test_rows_have_all_columns_and_valid_ranges():
    ds = synthetic_dataset(150, seed=0)
    scen = build_scenario(ds, seed=0, noise=0.05, n_records=500)
    rows = [run_exact(ds, scen), run_bloom(ds, scen, 1024, 4)]
    for r in rows:
        assert REQUIRED <= set(r), f"Missing: {REQUIRED - set(r)}"
        for m in ("f1", "precision", "recall", "reid_top1", "freq_success"):
            assert 0.0 <= r[m] <= 1.0
    assert rows[0]["precision"] == 1.0                      # exact hashes never give false positives
    # bloom row must have degenerate field
    bloom_row = rows[1]
    assert "degenerate" in bloom_row
    assert bloom_row["degenerate"] in (0, 1)


def test_no_noise_exact_matching_is_perfect_and_bf_is_close():
    ds = synthetic_dataset(150, seed=0)
    scen = build_scenario(ds, seed=0, noise=0.0, n_records=500)
    assert run_exact(ds, scen)["f1"] == 1.0
    assert run_bloom(ds, scen, 1024, 4)["f1"] > 0.95


def test_noisy_exact_hash_without_dictionary_matches():
    ds = synthetic_dataset(20, seed=0)
    scen = build_scenario(ds, seed=0, noise=0.15, n_records=60)
    scen = replace(scen, b_norm=[f"unmatched victim {i}" for i in range(len(scen.b_norm))])
    row = run_exact(ds, scen)
    assert row["reid_top1"] == row["reid_top5"] == 0
    for column in ("reid_ties", "reid_cands_delta", "reid_ties_count",
                   "reid_cands_delta_count", "reid_top1_conditional"):
        assert math.isnan(row[column])
    validate_results(pd.DataFrame([row]))


def test_fuzzy_beats_exact_under_noise():
    ds = synthetic_dataset(200, seed=0)
    scen = build_scenario(ds, seed=0, noise=0.15, n_records=500)
    assert run_bloom(ds, scen, 1024, 4)["f1"] > run_exact(ds, scen)["f1"] + 0.3


def test_collision_tuning_trades_utility_for_privacy():
    ds = synthetic_dataset(250, seed=0)
    scen = build_scenario(ds, seed=0, noise=0.05, n_records=800)
    std = run_bloom(ds, scen, 1024, 4)
    tight = run_bloom(ds, scen, 256, 15)
    assert tight["fill"] > std["fill"] and tight["load"] > std["load"]
    assert tight["reid_cands_delta"] > std["reid_cands_delta"]      # more plausible candidates = more ambiguity
    assert tight["f1"] <= std["f1"] + 1e-9                          # accuracy does not improve




def test_rq2_run_bloom_has_no_dp_fields():
    ds = synthetic_dataset(100, seed=0)
    scen = build_scenario(ds, seed=0, noise=0.05, n_records=300)
    row = run_bloom(ds, scen, 1024, 4)
    assert "eps" not in row
    assert "flip_p" not in row


def test_controlled_noise_loader_aligns_rq1_files():
    ds = controlled_noise_dataset(
        clean_path=str(Config.MASTER_PRODUCTS_PATH),
        noise_dir=str(Config.DATA_GENERATED_DIR),
        noise_level=0.05,
        seed=42,
        n=100,
    )
    assert ds.n == 100
    assert ds.noisy_norm is not None
    assert len(ds.noisy_norm) == ds.n
    assert ds.noise_level == 0.05
    assert ds.seed == 42


def test_real_frequency_weights_join_normalized_descriptions(tmp_path):
    master = tmp_path / "master.csv"
    shipments = tmp_path / "shipments.csv"
    master.write_text("raw_item_description\nAlpha pack\nBeta pack\n")
    shipments.write_text("item description\nALPHA PACK\nAlpha  Pack\nalpha pack\nOther item\n")
    ds = apply_real_frequency_counts(csv_dataset(master, "raw_item_description"), shipments)
    np.testing.assert_array_equal(ds.counts, [3, 1])
    np.testing.assert_allclose(ds.weights, [0.75, 0.25])


# --- New T1 tests ---

def test_saturated_config_produces_row_with_f1_unc():
    """A saturated config (l=256, k=30) must still produce a row; f1_unc >= 0."""
    import numpy as np
    ds = synthetic_dataset(200, seed=7)
    scen = build_scenario(ds, seed=7, noise=0.0, n_records=500)
    row = run_bloom(ds, scen, 256, 30)
    assert "f1_unc" in row
    assert row["f1_unc"] >= 0.0
    assert not np.isnan(row["f1_unc"])


def test_no_nan_in_f1_unc_multiple_configs():
    """f1_unc must never be NaN for any (l, k) bloom config."""
    import numpy as np
    ds = synthetic_dataset(200, seed=3)
    scen = build_scenario(ds, seed=3, noise=0.0, n_records=500)
    configs = [(1024, 4), (512, 15), (256, 30), (128, 50)]
    rows = [run_bloom(ds, scen, l, k) for l, k in configs]
    for row in rows:
        assert "f1_unc" in row
        assert not np.isnan(row["f1_unc"]), f"f1_unc is NaN for l={row['l']}, k={row['k']}"
