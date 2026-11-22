import math

import numpy as np
import pandas as pd
import pytest

from src.common.evaluation.aggregation import aggregate_runs, holm_adjust, paired_difference


def test_aggregate_sample_std_and_seed_counts():
    frame = pd.DataFrame({
        "seed": [0, 1, 2, 0], "method": ["a", "a", "a", "b"],
        "f1": [0.25, 0.5, 0.75, 0.6], "precision": [0.5, 0.5, 1.0, 1.0],
    })
    table = aggregate_runs(frame, ["method"], ["f1", "precision"]).set_index("method")
    assert table.loc["a", ["f1_mean", "f1_std", "n_seeds"]].tolist() == [0.5, 0.25, 3]
    assert table.loc["a", "precision_mean"] == pytest.approx(2 / 3)
    assert table.loc["a", "precision_std"] == pytest.approx(math.sqrt(1 / 12))
    assert table.loc["b", "f1_mean"] == 0.6
    assert table.loc["b", "n_seeds"] == 1 and pd.isna(table.loc["b", "f1_std"])


def test_holm_is_step_down_in_original_order_and_keeps_missing_family_slots():
    np.testing.assert_allclose(holm_adjust([0.04, 0.01, 0.03]), [0.06, 0.03, 0.06])
    np.testing.assert_allclose(holm_adjust([0.01, np.nan, 0.8]), [0.03, np.nan, 1.0])
    with pytest.raises(ValueError, match="p-values"):
        holm_adjust([-0.01, 0.2])


def test_pairing_wins_exact_tied_wilcoxon_and_t_interval():
    frame = pd.DataFrame(
        [(2, 0.05, "composite", "a", 0.4), (0, 0.05, "composite", "a", 0.6),
         (1, 0.05, "composite", "a", 0.7), (0, 0.05, "composite", "b", 0.5),
         (2, 0.05, "composite", "b", 0.5), (1, 0.05, "composite", "b", 0.5),
         (3, 0.05, "composite", "a", 1.0)],
        columns=["seed", "noise_level", "field_set", "method", "f1"],
    )
    row = paired_difference(frame, {"method": "a"}, lambda df: df.method.eq("b"), "f1").iloc[0]
    assert row["mean"] == pytest.approx(1 / 15)
    assert row["std"] == pytest.approx(math.sqrt(7 / 300))
    assert row["wins"] == 2 and row["n_seeds"] == 3
    margin = 4.302652729696142 * math.sqrt(7 / 900)
    assert row["ci_low"] == pytest.approx(1 / 15 - margin)
    assert row["ci_high"] == pytest.approx(1 / 15 + margin)
    assert row["p_value"] == pytest.approx(3 / 8)
    assert row["p_holm"] == 1


def test_pairing_holm_family_excludes_control_and_runs_per_field_set():
    rows = []
    for field in ("description", "composite"):
        for noise in (0.0, 0.05, 0.15, 0.30):
            for seed in range(4):
                diff = 0.04 * (seed + 1)
                rows.extend([
                    (seed, noise, field, "a", 0.5 + diff), (seed, noise, field, "b", 0.5)
                ])
    frame = pd.DataFrame(rows, columns=["seed", "noise_level", "field_set", "method", "f1"])
    result = paired_difference(frame, {"method": "a"}, {"method": "b"}, "f1")
    assert result.loc[result.noise_level.eq(0), "p_holm"].isna().all()
    assert result.loc[result.noise_level.gt(0), "p_holm"].eq(3 / 16).all()
    descriptive = paired_difference(frame, {"method": "a"}, {"method": "b"}, "f1", infer=False)
    assert descriptive[["p_value", "p_holm"]].isna().all().all()


def test_single_seed_interval_unavailable_and_zero_differences_have_p_one():
    frame = pd.DataFrame(
        [(0, 0.05, "composite", "fuzzy", 0.9), (0, 0.05, "composite", "exact", 0.9)],
        columns=["seed", "noise_level", "field_set", "method", "f1"],
    )
    row = paired_difference(frame, {"method": "fuzzy"}, {"method": "exact"}, "f1").iloc[0]
    assert row[["std", "ci_low", "ci_high"]].isna().all()
    assert row["p_value"] == row["p_holm"] == 1.0 and row["wins"] == 0
