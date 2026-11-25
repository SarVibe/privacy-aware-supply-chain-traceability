"""CSV contracts for the frozen v2 study."""

import json
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from src.common.experiment.io import require_columns, write_csv
from src.common.paths import app_dir
from src.rq2.collision_schema import CsvSchema
from src.rq2.collision_v2_metrics import E1, E2, EDGE, STRUCTURE

ID = ("variant", "noise", "seed", "l", "k")
GROUP = ("variant", "noise", "l", "k")
ACCURACY = ("precision", "recall", "f1")
UTILITY = (*ACCURACY, "pr_auc", "dice_overlap", "n_records", "n_entities", "n_pred_clusters")
MEASURES = ("tau", *UTILITY, *EDGE, *E1, *E2, *STRUCTURE)
EFFECTS = ("n_seeds", "mean_difference", "ci_low", "ci_high", "hodges_lehmann", "hl_ci_low",
           "hl_ci_high", "rank_biserial", "cohens_dz")
AGG = tuple(f"{name}_{stat}" for name in MEASURES for stat in ("mean", "std"))
CROSS = ("f1", "pr_auc", "direct_f1", "hit", "excess_matched", *E2)
CROSS_STATS = tuple(f"{name}_{stat}" for name in CROSS for stat in ("mean", "std", "delta_vs_baseline"))

V2_SCHEMAS = {
    "per_run": CsvSchema((*ID, *MEASURES), ID, frozenset(("pr_auc", "dice_overlap", "lift_matched"))),
    "aggregated": CsvSchema((*GROUP, "n_seeds", *AGG), GROUP, frozenset(AGG)),
    "exact_baseline": CsvSchema(("variant", "noise", "seed", *UTILITY), ("variant", "noise", "seed")),
    "e1": CsvSchema((*ID, "split", "frequency_source", *E1), (*ID, "split", "frequency_source"),
                     frozenset(("lift_matched",))),
    "e2": CsvSchema((*ID, "split", *E2, *STRUCTURE), (*ID, "split")),
    "controls": CsvSchema(("seed", "split", "l", "k", *E1, "random_hit", "random_gap", "random_trials"),
                          ("seed", "split"), frozenset(("lift_matched",))),
    "tau_sweeps": CsvSchema((*ID, "tau", *ACCURACY), (*ID, "tau")),
    "tau_sensitivity": CsvSchema((*ID, "split", "tau", "selected", *ACCURACY, *EDGE), (*ID, "split", "tau")),
    "validation": CsvSchema((*ID, "tau", "f1", "e2_precision_mean"), ID),
    "analytical": CsvSchema((*GROUP, "q_mean", "universe_size", "fill", "fill_finite", "fill_exponential", "f",
                             "u_times_f", "k_opt", "false_candidates_finite", "e2_false_candidates"), GROUP),
    "overlap": CsvSchema(("scope", "seed_a", "seed_b", "split_a", "split_b", "entities_a", "entities_b",
                          "entities_shared", "jaccard"), ("scope", "seed_a", "seed_b", "split_a", "split_b")),
    "paired_effects": CsvSchema(("l", "k", "metric", *EFFECTS), ("l", "k", "metric"), frozenset(("cohens_dz",))),
    "trends": CsvSchema(("hypothesis", "scope", "predictor", "outcome", "n_observations", "spearman_rho"),
                         ("hypothesis", "scope", "predictor", "outcome"), frozenset(("spearman_rho",))),
    "hypotheses": CsvSchema(("hypothesis", "scope", "verdict", "evidence"), ("hypothesis", "scope")),
    "h3": CsvSchema(("l", "k", "relative_reduction", "f1_difference", "ci_low", "ci_high", "qualifies"), ("l", "k")),
    "pareto": CsvSchema(("l", "k", "validation_f1", "validation_e2_precision", "validation_gap_ci_low",
                         "validation_gap_ci_high", "f1", "e2_precision_mean", "eligible", "near_tie",
                         "recommended", "extreme", "pareto"), ("l", "k")),
    "cross_check": CsvSchema((*GROUP, "n_seeds", *CROSS_STATS), GROUP,
                              frozenset(f"{name}_std" for name in CROSS)),
}
TEXT = {"variant", "split", "frequency_source", "metric", "hypothesis", "scope", "predictor", "outcome",
        "verdict", "evidence", "split_a", "split_b"}
FLAGS = {"selected", "qualifies", "eligible", "near_tie", "recommended", "extreme", "pareto"}
INTEGERS = {"seed", "seed_a", "seed_b", "l", "k", "used_bits", "n_seeds", "n_records", "n_entities",
            "n_pred_clusters", "universe_size", "random_trials", "n_observations", "entities_a", "entities_b",
            "entities_shared", *EDGE[3:]}
PROBS = {"noise", *ACCURACY, "validation_f1", "validation_e2_precision", "pr_auc", "dice_overlap",
         *EDGE[:3], "hit", "null_full", "null_matched", "random_hit", "random_gap", "fill", "fill_finite",
         "fill_exponential", "entropy", "f", "jaccard", E2[0], E2[1], E2[3]}
NONNEG = {"q_mean", "q_median", "ambiguity_mean", "ambiguity_median", "u_times_f", "k_opt",
          "false_candidates_finite", "e2_false_candidates", "lift_matched", "lift_full"}


def _v2_numeric(column, values, table):
    if column in PROBS:
        return values.between(0, 1).all()
    if column == "tau":
        return ((values > 0) & (values <= 1)).all()
    if column in INTEGERS:
        return (values >= 0).all() and (table == "analytical" or (values % 1 == 0).all())
    if column in NONNEG or column.endswith("_std"):
        return (values >= 0).all()
    if column in {"rank_biserial", "spearman_rho", "excess_full", "excess_matched", "f1_difference"}:
        return values.between(-1, 1).all()
    if table in {"aggregated", "cross_check"} and column.endswith("_mean"):
        metric = column.removesuffix("_mean")
        return (values >= 0).all() if metric in INTEGERS else _v2_numeric(metric, values, table)
    return True


def validate_v2_table(name: str, frame: pd.DataFrame) -> pd.DataFrame:
    schema = V2_SCHEMAS[name]
    require_columns(frame, schema.columns, table=name)
    if set(frame) != set(schema.columns) or (frame.empty and name != "tau_sensitivity"):
        raise ValueError(f"{name} has unexpected columns or no observations")
    if frame.duplicated(list(schema.key)).any():
        raise ValueError(f"{name} has duplicate row keys")
    for column in schema.columns:
        values = frame[column].dropna()
        if len(values) != len(frame) and column not in schema.nullable:
            raise ValueError(f"{name}.{column} requires non-null observations")
        if values.empty:
            continue
        if column in TEXT:
            valid = values.map(lambda value: isinstance(value, str) and bool(value)).all()
        elif column in FLAGS:
            valid = is_bool_dtype(values)
        else:
            valid = is_numeric_dtype(values) and not is_bool_dtype(values)
            valid = valid and np.isfinite(values).all() and _v2_numeric(column, values, name)
        if not valid:
            raise ValueError(f"{name}.{column} violates its declared domain")
    if {"l", "k"} <= set(frame) and ((frame["k"] < 1) | (frame["k"] > frame["l"])).any():
        raise ValueError(f"{name} requires 1 <= k <= l")
    return frame.loc[:, list(schema.columns)]


def export_v2_csv(name: str, rows, destination: Path) -> pd.DataFrame:
    if not isinstance(rows, pd.DataFrame):
        rows = pd.DataFrame.from_records(rows, columns=V2_SCHEMAS[name].columns) if not rows else pd.DataFrame(rows)
    table = validate_v2_table(name, rows)
    write_csv(table, destination / f"{name}.csv")
    return table


def verify_v1_freeze() -> dict[str, str]:
    root = app_dir().parents[1]
    expected = json.loads((root / "docs/v1_hashes.json").read_text(encoding="utf-8"))["sha256"]
    v1 = root / "backend/app/results/rq2"
    actual = {path.relative_to(root).as_posix() for path in v1.rglob("*") if path.is_file()}
    if actual != {name for name in expected if name.startswith("backend/app/results/rq2/")}:
        raise ValueError("The frozen v1 result directory differs from the manifest")
    for name, digest in expected.items():
        if sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Frozen artifact differs from the manifest: {name}")
    return expected
