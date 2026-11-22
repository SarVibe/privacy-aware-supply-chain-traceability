import math
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
import pytest

from src.rq2.parameter_validation import (
    validate_eps, validate_noise, validate_overlap, validate_n_records,
    validate_bit_top, validate_dataset, validate_tau, validate_bloom_parameters,
)
from src.common.noise_injection import add_typos, NoiseSpec
from src.rq2.numpy_randomized_response import flip_probability
from src.rq2.results_schema import validate_results, SchemaError
from src.rq2.rq2_dataset import synthetic_dataset
from experiments.rq2.results_analyzer import holm_bonferroni, merge_paired


@pytest.mark.parametrize("eps", [float("nan"), -1.0, 0.0])
def test_invalid_eps(eps):
    with pytest.raises(ValueError):
        validate_eps(eps)


def test_extreme_eps():
    assert flip_probability(1e9, 4) == 0.0
    assert abs(flip_probability(1e-9, 4) - 0.5) < 1e-10
    assert flip_probability(math.inf, 4) == 0.0


@pytest.mark.parametrize("rate", [-0.1, 7.0, float("nan")])
def test_noise_bounds(rate):
    with pytest.raises(ValueError):
        validate_noise(rate)


@pytest.mark.parametrize("overlap", [0.0, -0.1, 1.1, float("nan")])
def test_overlap_bounds(overlap):
    with pytest.raises(ValueError):
        validate_overlap(overlap)


@pytest.mark.parametrize("value", [0, -1])
def test_invalid_n_records(value):
    with pytest.raises(ValueError):
        validate_n_records(value)


def test_invalid_bit_top():
    with pytest.raises(ValueError):
        validate_bit_top(0)


def test_small_dataset():
    ds = synthetic_dataset(3, seed=0)
    with pytest.raises(ValueError):
        validate_dataset(ds)


@pytest.mark.parametrize("min_len", [0, 3])
def test_noise_short_strings(min_len):
    rng = np.random.default_rng(0)
    spec = NoiseSpec(rate=0.3, min_len=min_len)
    if min_len == 3:
        assert add_typos("abc", 0.3, rng, spec) == "abc"
    else:
        assert add_typos("a", 0.3, rng, spec) == "a" or len(add_typos("a", 0.3, rng, spec)) >= 1


def test_shared_noise_vendor_present():
    path = Path(__file__).resolve().parents[2] / "src" / "common" / "noise_injection.py"
    assert "inject_typo" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("tau", [0.30, 0.70, 0.80, 0.95, 0.99])
def test_rq2_tau_boundaries(tau):
    assert validate_tau(tau) == tau


@pytest.mark.parametrize("tau", [0.299, 0.991, float("nan")])
def test_rq2_tau_outside_bounds(tau):
    with pytest.raises(ValueError):
        validate_tau(tau)


@pytest.mark.parametrize(
    ("l", "k"),
    [(128, 2), (256, 4), (1024, 30), (2048, 50), (1024, 4)],
)
def test_rq2_bloom_parameter_boundaries(l, k):
    assert validate_bloom_parameters(l, k) == (l, k)


@pytest.mark.parametrize(
    ("l", "k"),
    [(127, 4), (2049, 4), (256, 1), (256, 51), (256, 257)],
)
def test_rq2_bloom_parameters_outside_bounds(l, k):
    with pytest.raises(ValueError):
        validate_bloom_parameters(l, k)


def base_schema_df():
    base = {
        "method": ["bloom", "bloom"],
        "l": [1024, 1024],
        "k": [4, 4],
        "q": [2, 2],
        "noise": [0.05, 0.05],
        "seed": [0, 1],
        "overlap": [1.0, 1.0],
        "eps": [float("inf"), float("inf")],
        "precision": [0.8, 0.8],
        "recall": [0.8, 0.8],
        "f1": [0.8, 0.8],
        "fpr": [0.1, 0.1],
        "auc": [0.9, 0.9],
        "reid_top1": [0.2, 0.2],
        "reid_top5": [0.3, 0.3],
        "reid_cands_delta": [1.0, 1.0],
        "freq_success": [0.1, 0.1],
        "bit_success": [0.1, 0.1],
        "fill": [0.2, 0.2],
        "entropy": [0.8, 0.8],
    }
    return pd.DataFrame(base)


def test_schema_missing_columns():
    with pytest.raises(SchemaError):
        validate_results(pd.DataFrame({"method": ["bloom"]}))


def test_schema_duplicate_records():
    df = base_schema_df()
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    with pytest.raises(SchemaError):
        validate_results(df)


def test_schema_invalid_nan():
    df = base_schema_df()
    df.loc[0, "fill"] = np.nan
    with pytest.raises(SchemaError):
        validate_results(df)


@pytest.mark.parametrize("column", ["reid_ties", "reid_cands_delta", "reid_ties_count", "reid_cands_delta_count"])
def test_schema_rejects_finite_candidate_counts_below_one(column):
    df = base_schema_df()
    df[column] = [np.nan, 0.0]
    with pytest.raises(SchemaError, match=f"{column} contains counts below 1"):
        validate_results(df)


def test_schema_imbalanced_seeds():
    df = base_schema_df()
    df = df[df["method"] == "bloom"]
    df2 = pd.concat([df, pd.DataFrame([df.iloc[0].to_dict() | {"k": 8, "seed": 2}])], ignore_index=True)
    assert validate_results(df2) is not None


def test_holm_known_example():
    adjusted = holm_bonferroni(np.array([0.01, 0.04, 0.03]))
    assert np.allclose(adjusted, [0.03, 0.06, 0.06])


def test_paired_seed_alignment():
    a = pd.DataFrame({"seed": [0, 1], "f1": [0.8, 0.9]})
    b = pd.DataFrame({"seed": [0, 2], "f1": [0.7, 0.8]})
    with pytest.raises(ValueError):
        merge_paired(a, b, "f1")
