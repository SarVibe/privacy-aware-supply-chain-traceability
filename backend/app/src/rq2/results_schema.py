from dataclasses import dataclass

import numpy as np
import pandas as pd
from src.common.experiment.io import require_columns


@dataclass
class SchemaError(ValueError):
    messages: list[str]

    def __str__(self):
        return "Results CSV validation failed:\n- " + "\n- ".join(self.messages)


REQUIRED_COLUMNS = (
    "method", "l", "k", "q", "noise", "seed", "overlap",
    "precision", "recall", "f1", "fpr", "auc", "reid_top1",
    "reid_top5", "reid_cands_delta", "freq_success", "bit_success",
    "fill", "entropy",
)

BOUNDED_COLUMNS = (
    "precision", "recall", "f1", "fpr", "auc", "reid_top1",
    "reid_top5", "reid_top1_conditional", "freq_success",
    "bit_success", "fill",
    "cross_party_precision", "cross_party_recall", "cross_party_f1", "cross_party_fpr",
)


def validate_results(df: pd.DataFrame) -> pd.DataFrame:
    errors = []
    if df is None or not isinstance(df, pd.DataFrame):
        raise SchemaError(["results must be a pandas DataFrame"])

    try:
        require_columns(df, REQUIRED_COLUMNS, table="Results CSV")
    except ValueError as exc:
        errors.append(str(exc))

    if not errors:
        numeric = ("l", "k", "q", "noise", "seed", "overlap",
                   "precision", "recall", "f1", "fpr", "auc",
                   "reid_top1", "reid_top5", "reid_cands_delta",
                   "freq_success", "bit_success", "fill", "entropy")
        numeric += tuple(column for column in BOUNDED_COLUMNS if column.startswith("cross_party_"))
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
        for c in ("reid_ties", "reid_cands_delta", "reid_ties_count", "reid_cands_delta_count"):
            if c not in df.columns:
                continue
            values = pd.to_numeric(df[c], errors="coerce")
            if (np.isfinite(values) & (values < 1)).any():
                errors.append(f"{c} contains counts below 1")

        key = ("method", "l", "k", "noise", "overlap", "seed", "data_mode")
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
            exact = df[df["method"] == "exact_hash"]
            if not exact.empty:
                seed_sets = [
                    set(g["seed"].dropna().astype(int))
                    for _, g in exact.groupby(
                        [c for c in ("noise", "overlap") if c in exact.columns],
                        dropna=False,
                    )
                ]
                if seed_sets:
                    first = seed_sets[0]
                    if any(s != first for s in seed_sets[1:]):
                        errors.append("exact baseline configurations have imbalanced seed sets")

    if errors:
        raise SchemaError(errors)
    return df
