"""Exercise the result validator through real CSV reads."""

from dataclasses import replace
from itertools import product

import pandas as pd
import pytest

from experiments.rq1 import validate_rq1_results as validator
from experiments.rq1.run_rq1 import RAW_COLUMNS, TAU_COLUMNS, _thresholds
from src.common.config import load_config
from src.common.experiment.io import write_csv


@pytest.fixture
def files(tmp_path, monkeypatch):
    cfg = replace(load_config("rq1"), seeds=(0, 1))
    monkeypatch.setattr(validator, "load_config", lambda _: cfg)
    raw, tuning = [], []
    for seed, level, field in product(cfg.seeds, cfg.noise_levels, cfg.field_sets):
        score = 0.95 - level
        for method, mode, tau in (
            ("raw_exact", "none", None), ("normalized_exact", "none", None),
            ("bloom_fuzzy", "single", 0.92), ("bloom_fuzzy", "per_noise", 0.92),
        ):
            raw.append((
                f"{seed}-{level}-{field}-{method}-{mode}", seed, level, method, field,
                tau, mode, "test", score, score, score, 1.2, 100, 30, 34, 0.01,
            ))
        for tau in _thresholds(cfg.tau_grid):
            score_at_tau = 0.9 if tau == 0.92 else 0.8
            tuning.append((seed, field, level, tau, score_at_tau, score_at_tau, score_at_tau))
    return (
        pd.DataFrame(raw, columns=RAW_COLUMNS),
        pd.DataFrame(tuning, columns=TAU_COLUMNS),
        tmp_path / "raw.csv", tmp_path / "tau.csv",
    )


def _run(files) -> int:
    raw, tuning, raw_path, tau_path = files
    write_csv(raw, raw_path)
    write_csv(tuning, tau_path)
    return validator.main(["--input", str(raw_path), "--tau-input", str(tau_path)])


def test_complete_result_passes(files, capsys):
    assert _run(files) == 0
    output = capsys.readouterr().out
    assert "FAIL:" not in output and "WARN:" not in output
    assert "64 rows" in output and "Test cutoffs match the validation-only selections" in output


@pytest.mark.parametrize(
    ("column", "bad_value", "message"),
    [
        ("runtime_sec", "text", "dtypes"),
        ("split", "validation", "Only the test split"),
        ("f1", 1.1, "Precision, recall and F1"),
        ("fragmentation_rate", 0.5, "defined fragmentation"),
        ("tau", 0.92, "Only fuzzy rows have tau"),
    ],
)
def test_broken_raw_values_fail(files, capsys, column, bad_value, message):
    raw = files[0]
    if isinstance(bad_value, str):
        raw[column] = raw[column].astype(object)
    raw.loc[0, column] = bad_value
    assert _run(files) == 1
    assert any("FAIL:" in line and message in line for line in capsys.readouterr().out.splitlines())


def test_duplicate_id_and_missing_row_fail(files, capsys):
    raw = files[0]
    raw.loc[1, "run_id"] = raw.loc[0, "run_id"]
    raw.drop(index=2, inplace=True)
    assert _run(files) == 1
    output = capsys.readouterr().out
    assert "FAIL: Run IDs are unique" in output
    assert "FAIL: Raw grid" in output


def test_missing_required_column_fails(files, capsys):
    files[0].drop(columns="precision", inplace=True)
    assert _run(files) == 1
    assert "FAIL: Raw results have the required schema" in capsys.readouterr().out


def test_missing_tuning_grid_row_and_wrong_test_tau_fail(files, capsys):
    raw, tuning, _, _ = files
    raw.loc[raw.tau_mode.eq("single"), "tau"] = 0.91
    assert _run(files) == 1
    assert "FAIL: Test cutoffs match" in capsys.readouterr().out
    tuning.drop(index=0, inplace=True)
    assert _run(files) == 1
    assert "FAIL: Validation tuning covers" in capsys.readouterr().out


def test_boundary_variation_and_rising_exact_f1_warn(files, capsys):
    raw, tuning, _, _ = files
    raw.loc[raw.tau.notna(), "tau"] = 0.99
    tuning["f1"] = tuning.tau.eq(0.99).astype(float)
    changed = raw.method.eq("raw_exact") & raw.noise_level.eq(0.30)
    raw.loc[changed, "f1"] = raw.loc[changed, "seed"].map({0: 0.94, 1: 1.0})
    varied = raw.method.eq("bloom_fuzzy") & raw.noise_level.eq(0.15) & raw.seed.eq(0)
    raw.loc[varied, "f1"] = 0.50
    assert _run(files) == 0
    output = capsys.readouterr().out
    assert "WARN: Single-tau boundary choices" in output
    assert "WARN: Exact mean F1 rises" in output
    assert "WARN: F1 sample SD exceeds" in output
