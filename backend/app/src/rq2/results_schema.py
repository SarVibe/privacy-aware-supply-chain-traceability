from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass
class SchemaError(ValueError):
    messages: list[str]

    def __str__(self):
        return "Results CSV validation failed:\n- " + "\n- ".join(self.messages)


REQUIRED_COLUMNS = (
    "method", "l", "k", "q", "noise", "seed", "overlap", "eps",
    "precision", "recall", "f1", "fpr", "auc", "reid_top1",
    "reid_top5", "reid_cands_delta", "freq_success", "bit_success",
    "fill", "entropy",
)

BOUNDED_COLUMNS = (
    "precision", "recall", "f1", "fpr", "auc", "reid_top1",
    "reid_top5", "reid_ties", "reid_cands_delta", "freq_success",
    "bit_success", "fill",
)


def validate_results(df: pd.DataFrame) -> pd.DataFrame:
    errors = []
    if df is None or not isinstance(df, pd.DataFrame):
        raise SchemaError(["results must be a pandas DataFrame"])

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        errors.append("missing required columns: " + ", ".join(missing))

    if not errors:
        numeric = ("l", "k", "q", "noise", "seed", "overlap", "eps",
                   "precision", "recall", "f1", "fpr", "auc",
                   "reid_top1", "reid_top5", "reid_cands_delta",
                   "freq_success", "bit_success", "fill", "entropy")
        for c in numeric:
            if c in df.columns and not pd.api.types.is_numeric_dtype(df[c]):
                errors.append(f"{c} must be numeric")

        for c in BOUNDED_COLUMNS:
            if c not in df.columns:
                continue
            values = pd.to_numeric(df[c], errors="coerce")
            bad = values.notna() & ((values < 0) | (values > 1))
            if bad.any():
                errors.append(f"{c} contains values outside [0,1]")

        key = ("method", "l", "k", "noise", "overlap", "eps", "seed", "data_mode")
        present = [c for c in key if c in df.columns]
        if present:
            duplicate_mask = df.duplicated(subset=present, keep=False)
            if duplicate_mask.any():
                errors.append("duplicate configurations found")

        if "method" in df.columns:
            exact = df["method"] == "exact_hash"
            bloom = df["method"] == "bloom"
            exact_nan_ok = ("tau", "auc", "fill", "entropy", "bit_success",
                            "bit_baseline", "bit_qgrams_per_bit")
            for c in exact_nan_ok:
                if c in df.columns and df.loc[bloom, c].isna().any():
                    errors.append(f"bloom rows contain NaN in {c}")

        if "method" in df.columns and "seed" in df.columns:
            bloom = df[df["method"] == "bloom"]
            if not bloom.empty:
                seed_sets = [
                    set(g["seed"].dropna().astype(int))
                    for _, g in bloom.groupby(
                        [c for c in ("l", "k", "noise", "overlap", "eps") if c in bloom],
                        dropna=False,
                    )
                ]
                if seed_sets:
                    first = seed_sets[0]
                    if any(s != first for s in seed_sets[1:]):
                        errors.append("bloom configurations have imbalanced seed sets")

    if errors:
        raise SchemaError(errors)
    return df
