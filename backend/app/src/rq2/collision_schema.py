"""Explicit schemas for all collision-study CSV artifacts."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from src.common.experiment.io import require_columns, write_csv
from src.rq2.collision_gate import GATE_METRICS

PRF = ("precision", "recall", "f1")
CROSS_PRF = tuple(f"cross_party_{metric}" for metric in PRF)
HISTORICAL = ("historical_tau", *(f"historical_{metric}" for metric in PRF))
KEYS = ("variant", "noise", "seed", "method", "l", "k")
ATTACK_KEYS = (*KEYS, "split", "attack")
STRUCTURAL = ("fill", "fill_expected", "entropy", "q_mean", "q_median", "universe_size", "collision_proxy",
              "false_candidate_proxy", "ambiguity_mean", "ambiguity_median")
EMPIRICAL = ("attack_success", "random_baseline", "lift", "used_bits")
RUN_METRICS = (*GATE_METRICS, *CROSS_PRF, "pr_auc", "dice_overlap", "tau", *HISTORICAL,
               *STRUCTURAL, *EMPIRICAL)
GROUP_KEYS = tuple(name for name in KEYS if name != "seed")
COMPARISON = ("attack_success", "f1", "precision", "recall", "pr_auc", "dice_overlap", "fill")
PROBABILITIES = {*PRF, *CROSS_PRF, *HISTORICAL, "tau", "pr_auc", "dice_overlap", "noise", "fill",
                 "fill_expected", "entropy", "attack_success", "random_baseline", "collision_proxy"}
NONNEGATIVE = {"fragmentation_rate", "q_mean", "q_median", "false_candidate_proxy", "ambiguity_mean",
               "ambiguity_median", "lift", "min_lift", "random_gap", "max_random_gap", "random_control_mean"}
COUNTS = {"seed", "n_records", "n_entities", "n_pred_clusters", "universe_size", "used_bits", "l", "k",
          "n_seeds", "n_pairs", "permutations"}
LABELS = {"variant", "method", "split", "attack", "metric", "hypothesis", "scope", "predictor", "outcome"}
FLAGS = {"passed", "pareto", "recommended", "eligible", "near_tie", "extreme"}


@dataclass(frozen=True)
class CsvSchema:
    columns: tuple[str, ...]
    key: tuple[str, ...]
    nullable: frozenset[str] = frozenset()


_RUN_NULLS = frozenset((*HISTORICAL, "tau", "pr_auc", "dice_overlap", "fragmentation_rate", *STRUCTURAL, *EMPIRICAL))
_PARETO_METRICS = ("attack_success", "f1", "validation_attack_success", "validation_f1", "attack_gap_ci_low",
                   "attack_gap_ci_high")
_SUMMARY_COLUMNS = tuple(f"{metric}_{stat}" for metric in RUN_METRICS for stat in ("mean", "std"))
_EFFECT_METRICS = ("mean_difference", "ci_low", "ci_high", "hodges_lehmann", "hl_ci_low", "hl_ci_high",
                   "rank_biserial", "cohens_dz")
SCHEMAS = {
    "regression_gate": CsvSchema(("seed", "noise", "l", "k", "tau", *GATE_METRICS,
                                   "q_mean", "q_median", "universe_size", "passed"), ("seed",)),
    "per_run": CsvSchema((*KEYS, *RUN_METRICS), KEYS, _RUN_NULLS),
    "aggregated": CsvSchema((*GROUP_KEYS, "n_seeds", *_SUMMARY_COLUMNS), GROUP_KEYS, frozenset(_SUMMARY_COLUMNS)),
    "attack_results": CsvSchema((*ATTACK_KEYS, *EMPIRICAL), ATTACK_KEYS),
    "controls": CsvSchema(("seed", "split", "l", "k", *EMPIRICAL, "min_lift", "permutations",
                           "random_control_mean", "random_gap", "max_random_gap", "passed"), ("seed", "split")),
    "tau_sweeps": CsvSchema((*KEYS, "tau", *GATE_METRICS), (*KEYS, "tau"), frozenset(("fragmentation_rate",))),
    "pareto": CsvSchema(("l", "k", *_PARETO_METRICS, "pareto", "eligible", "recommended", "near_tie", "extreme"),
                        ("l", "k")),
    "cross_check": CsvSchema(
        ("variant", "noise", "l", "k", "n_seeds",
         *(f"{metric}_{suffix}" for metric in COMPARISON for suffix in ("mean", "std", "delta_vs_baseline"))),
        ("variant", "noise", "l", "k"),
        frozenset(f"{metric}_std" for metric in COMPARISON),
    ),
    "paired_effects": CsvSchema(("l", "k", "metric", "n_seeds", *_EFFECT_METRICS), ("l", "k", "metric"),
                                frozenset(("cohens_dz",))),
    "trends": CsvSchema(("hypothesis", "scope", "predictor", "outcome", "n_pairs", "spearman_rho"),
                        ("hypothesis", "scope", "predictor", "outcome"), frozenset(("spearman_rho",))),
}


def _numeric_domain(name, values):
    if name in COUNTS:
        return ((values >= 0) & (values % 1 == 0)).all()
    if name in PROBABILITIES or name in {"validation_attack_success", "validation_f1"}:
        return values.between(0, 1).all() and (name not in {"tau", "historical_tau"} or (values > 0).all())
    if name in NONNEGATIVE or name.endswith("_std"):
        return (values >= 0).all()
    if name in {"rank_biserial", "spearman_rho"}:
        return values.between(-1, 1).all()
    if name.endswith("_mean"):
        metric = name.removesuffix("_mean")
        return (values >= 0).all() if metric in COUNTS else _numeric_domain(metric, values)
    return True


def validate_collision_csv(name: str, frame: pd.DataFrame) -> pd.DataFrame:
    schema = SCHEMAS[name]
    require_columns(frame, schema.columns, table=name)
    if frame.empty or set(frame.columns) != set(schema.columns):
        raise ValueError(f"{name} requires nonempty rows and exactly its declared columns")
    if frame.duplicated(list(schema.key)).any():
        raise ValueError(f"{name} has duplicate primary keys")
    for column in schema.columns:
        data = frame[column]
        values = data.dropna()
        if column not in schema.nullable and len(values) != len(data):
            raise ValueError(f"{name}.{column} requires non-null values")
        if values.empty:
            continue
        if column in FLAGS:
            valid = is_bool_dtype(values)
        elif column in LABELS:
            valid = values.map(lambda value: isinstance(value, str) and bool(value)).all()
        else:
            valid = is_numeric_dtype(values) and not is_bool_dtype(values)
            valid = valid and np.isfinite(values).all() and _numeric_domain(column, values)
        if not valid:
            raise ValueError(f"{name}.{column} contains values outside its declared domain")
    if {"l", "k"}.issubset(frame):
        exact = frame["method"].eq("exact") if "method" in frame else pd.Series(False, index=frame.index)
        if not (frame.loc[exact, ["l", "k"]] == 0).all().all():
            raise ValueError(f"{name} exact rows require l=k=0")
        bloom = frame.loc[~exact]
        if ((bloom["k"] < 1) | (bloom["k"] > bloom["l"])).any():
            raise ValueError(f"{name} requires 1 <= k <= l for Bloom rows")
    return frame.loc[:, list(schema.columns)]


def write_collision_csv(name: str, frame: pd.DataFrame, directory: Path) -> None:
    write_csv(validate_collision_csv(name, frame), directory / f"{name}.csv")
