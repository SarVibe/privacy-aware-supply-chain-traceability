import math

import numpy as np

from src.rq2.rq2_dataset import synthetic_dataset
from src.rq2.privacy_pipeline import build_scenario, run_bloom, run_exact
from src.rq2.rq2_dataset import controlled_noise_dataset
from src.application_config import Config

REQUIRED = {"method", "l", "k", "noise", "seed", "f1", "precision", "recall", "auc", "reid_top1", "reid_top5",
            "reid_cands_delta", "freq_success", "bit_success", "fill", "entropy", "load", "tau", "eps"}


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
        assert REQUIRED <= set(r)
        assert "degenerate" not in r
        for m in ("f1", "precision", "recall", "reid_top1", "freq_success"):
            assert 0.0 <= r[m] <= 1.0
    assert rows[0]["precision"] == 1.0                      # exact hashes never give false positives


def test_no_noise_exact_matching_is_perfect_and_bf_is_close():
    ds = synthetic_dataset(150, seed=0)
    scen = build_scenario(ds, seed=0, noise=0.0, n_records=500)
    assert run_exact(ds, scen)["f1"] == 1.0
    assert run_bloom(ds, scen, 1024, 4)["f1"] > 0.95


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


def test_dp_reduces_attack_success_and_utility():
    ds = synthetic_dataset(200, seed=0)
    # noise=0: stored records of one entity are identical, so the frequency attack is meaningful
    scen = build_scenario(ds, seed=0, noise=0.0, n_records=2000)
    clean = run_bloom(ds, scen, 1024, 4)
    assert clean["freq_success"] > 0.2
    noisy = run_bloom(ds, scen, 1024, 4, eps=4.0)
    assert math.isclose(noisy["flip_p"], 1 / (1 + math.exp(1.0)))
    assert noisy["f1"] < clean["f1"] and noisy["freq_success"] < clean["freq_success"]


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
