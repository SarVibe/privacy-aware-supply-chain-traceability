"""Validate the frozen RQ1 run and its validation threshold table."""

import argparse
from collections.abc import Sequence
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.rq1.run_rq1 import RAW_COLUMNS, TAU_COLUMNS, _thresholds
from src.common.config import Config, load_config
from src.common.experiment.io import read_csv
from src.common.linking.exact import NORMALIZED_EXACT, RAW_EXACT
from src.common.linking.threshold import select_per_noise_tau, select_single_tau
from src.common.paths import results_dir

_FUZZY = "bloom_fuzzy"
_COUNTS = ("n_records", "n_entities", "n_pred_clusters")
_SCORES = ("precision", "recall", "f1")
_RAW_TEXT = ("run_id", "method", "field_set", "tau_mode", "split")
_MODES = ((RAW_EXACT, "none"), (NORMALIZED_EXACT, "none"), (_FUZZY, "single"), (_FUZZY, "per_noise"))
_RAW_KEYS = ("seed", "noise_level", "field_set", "method", "tau_mode")
_TAU_KEYS = ("seed", "field_set", "noise_level", "tau")


def _dtypes(frame: pd.DataFrame, text_columns: tuple[str, ...], columns: tuple[str, ...]) -> bool:
    return (
        all(frame[column].map(lambda value: isinstance(value, str) and bool(value.strip())).all()
            for column in text_columns)
        and all(pd.api.types.is_numeric_dtype(frame[column]) and not pd.api.types.is_bool_dtype(frame[column])
                for column in columns if column not in text_columns)
        and all(pd.api.types.is_integer_dtype(frame[column])
                for column in ("seed", *[col for col in _COUNTS if col in columns]))
    )


def _scores_in_range(df: pd.DataFrame) -> bool:
    return bool(df[list(_SCORES)].apply(lambda values: values.between(0, 1)).all().all())


def _expected_runs(cfg: Config) -> set[tuple]:
    return {(seed, level, field, method, mode)
            for seed, level, field, (method, mode) in product(cfg.seeds, cfg.noise_levels, cfg.field_sets, _MODES)}


def _matches_validation(raw: pd.DataFrame, tuning: pd.DataFrame) -> bool:
    for (seed, field), table in tuning.groupby(["seed", "field_set"], sort=False):
        rows = raw.loc[raw.seed.eq(seed) & raw.field_set.eq(field) & raw.method.eq(_FUZZY)]
        single, per_noise = select_single_tau(table), select_per_noise_tau(table)
        if not rows.loc[rows.tau_mode.eq("single"), "tau"].eq(single).all():
            return False
        sensitivity = rows.loc[rows.tau_mode.eq("per_noise")]
        if not sensitivity.tau.eq(sensitivity.noise_level.map(per_noise)).all():
            return False
    return True


def validate_results(
    raw: pd.DataFrame, tuning: pd.DataFrame, cfg: Config
) -> list[tuple[str, str]]:
    """Return named PASS, FAIL, and WARN checks for a complete RQ1 result."""
    checks = []

    def check(ok: bool, message: str) -> None:
        checks.append(("PASS" if ok else "FAIL", message))

    raw_columns = tuple(raw.columns) == RAW_COLUMNS
    tau_columns = tuple(tuning.columns) == TAU_COLUMNS
    check(raw_columns, "Raw results have the required schema and column order")
    check(tau_columns, "Tuning results have the required schema and column order")
    if not (raw_columns and tau_columns):
        return checks
    raw_types = _dtypes(raw, _RAW_TEXT, RAW_COLUMNS)
    tau_types = _dtypes(tuning, ("field_set",), TAU_COLUMNS)
    check(raw_types, "Raw numeric columns and text labels have the required dtypes")
    check(tau_types, "Tuning numeric columns and field labels have the required dtypes")
    if not (raw_types and tau_types):
        return checks

    grid = _thresholds(cfg.tau_grid)
    expected_runs = _expected_runs(cfg)
    run_grid = set(raw[list(_RAW_KEYS)].itertuples(index=False, name=None))
    check(len(raw) == len(expected_runs) and run_grid == expected_runs,
          f"Raw grid has exactly {len(expected_runs)} rows and the required combinations (found {len(raw)})")
    expected_tuning = set(product(cfg.seeds, cfg.field_sets, cfg.noise_levels, grid))
    tuning_grid = set(tuning[list(_TAU_KEYS)].itertuples(index=False, name=None))
    tuning_coverage = len(tuning) == len(expected_tuning) and tuning_grid == expected_tuning
    check(tuning_coverage, f"Validation tuning covers exactly {len(expected_tuning)} grid rows (found {len(tuning)})")
    check(bool(len(raw)) and raw.split.eq("test").all(), "Only the test split appears in raw results")
    check(raw.run_id.is_unique, "Run IDs are unique")

    fragmentation = raw.fragmentation_rate
    valid_fragmentation = fragmentation.isna().eq(raw.n_records.eq(raw.n_entities)).all()
    valid_fragmentation &= (np.isfinite(fragmentation.dropna()) & fragmentation.dropna().ge(1)).all()
    check(_scores_in_range(raw) and _scores_in_range(tuning) and valid_fragmentation,
          "Precision, recall and F1 are in [0, 1] and defined fragmentation is at least 1")
    count_ranges = (raw[list(_COUNTS)].gt(0).all().all()
                    and raw.n_entities.le(raw.n_records).all() and raw.n_pred_clusters.le(raw.n_records).all())
    check(count_ranges and (np.isfinite(raw.runtime_sec) & raw.runtime_sec.ge(0)).all(),
          "Record, entity and cluster counts and runtimes are valid")

    fuzzies = raw.loc[raw.method.eq(_FUZZY)]
    exact = raw.loc[raw.method.isin((RAW_EXACT, NORMALIZED_EXACT))]
    tau_ok = exact.tau.isna().all() and fuzzies.tau.isin(grid).all()
    check(tau_ok, "Only fuzzy rows have tau and their cutoffs belong to the configured grid")
    if len(raw) == len(expected_runs) and run_grid == expected_runs and tuning_coverage and _scores_in_range(tuning):
        check(_matches_validation(raw, tuning), "Test cutoffs match the validation-only selections")

    single = fuzzies.loc[fuzzies.tau_mode.eq("single")].drop_duplicates(["seed", "field_set"])
    if len(single):
        boundary = int(single.tau.isin((grid[0], grid[-1])).sum())
        share = boundary / len(single)
        checks.append(("WARN" if share > 0.20 else "PASS",
                       f"Single-tau boundary choices: {boundary}/{len(single)} ({share:.1%})"))

    means = exact.groupby(["method", "field_set", "noise_level"]).f1.mean().sort_index()
    rises = means.groupby(level=["method", "field_set"]).diff().gt(1e-12)
    rising_groups = sorted({f"{method}/{field}" for method, field, _ in rises[rises].index})
    if rising_groups:
        checks.append(("WARN", f"Exact mean F1 rises with noise in {', '.join(rising_groups)}"))
    else:
        checks.append(("PASS", "Exact mean F1 does not rise with noise"))

    deviations = raw.groupby(["method", "field_set", "tau_mode", "noise_level"]).f1.std()
    high = deviations[deviations > 0.05]
    if len(high):
        checks.append(("WARN", f"F1 sample SD exceeds 0.05 in {len(high)} groups (maximum {high.max():.4f})"))
    else:
        checks.append(("PASS", "No seed-level F1 sample SD exceeds 0.05"))
    return checks


def main(argv: Sequence[str] | None = None) -> int:
    """Print validator checks and exit nonzero on failure."""
    cfg = load_config("rq1")
    default = results_dir(cfg, "rq1")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=default / "raw_runs.csv")
    parser.add_argument("--tau-input", type=Path, default=default / "tau_selection.csv")
    args = parser.parse_args(argv)
    try:
        checks = validate_results(read_csv(args.input), read_csv(args.tau_input), cfg)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    for status, message in checks:
        print(f"{status}: {message}")
    return int(any(status == "FAIL" for status, _ in checks))


if __name__ == "__main__":
    raise SystemExit(main())
