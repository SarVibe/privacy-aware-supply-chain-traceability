"""Aggregate experiment runs and compare matched seed-level outcomes."""

from collections.abc import Callable, Mapping, Sequence
from math import sqrt

import numpy as np
import pandas as pd
from scipy.stats import PermutationMethod, rankdata, t, wilcoxon

HYPOTHESIS_NOISE_LEVELS = (0.05, 0.15, 0.30)
_SEED = "seed"
_NOISE = "noise_level"
_FIELD_SET = "field_set"
_RunFilter = Mapping[str, object] | Callable[[pd.DataFrame], pd.Series]


def aggregate_runs(df: pd.DataFrame, group_cols: Sequence[str], metrics: Sequence[str]) -> pd.DataFrame:
    """Report each metric's mean and sample standard deviation, plus distinct seed counts."""
    columns = {
        f"{metric}_{stat}": (metric, stat)
        for metric in metrics
        for stat in ("mean", "std")
    }
    grouped = df.groupby(list(group_cols), sort=False, dropna=False, observed=True)
    return grouped.agg(**columns, n_seeds=(_SEED, "nunique")).reset_index()


def holm_adjust(p_values: Sequence[float]) -> np.ndarray:
    """Adjust p-values in input order, reserving a family slot for each missing result."""
    original = np.asarray(p_values, dtype=float)
    if original.ndim != 1 or ((original < 0) | (original > 1)).any():
        raise ValueError("Holm adjustment requires a one-dimensional sequence of p-values in [0, 1]")
    order = np.argsort(original, kind="stable")
    ranked = np.nan_to_num(original[order], nan=1.0)
    corrected = np.minimum(1.0, np.maximum.accumulate(ranked * np.arange(len(ranked), 0, -1)))
    adjusted = np.empty_like(original)
    adjusted[order] = corrected
    adjusted[np.isnan(original)] = np.nan
    return adjusted


def _select(df: pd.DataFrame, criteria: _RunFilter) -> pd.DataFrame:
    if callable(criteria):
        return df.loc[criteria(df)]
    mask = pd.Series(True, index=df.index)
    for column, value in criteria.items():
        mask &= df[column].eq(value)
    return df.loc[mask]


def _wilcoxon_greater(differences: np.ndarray) -> float:
    # Round subtraction artefacts before ranking. The Wilcox rule drops exact zero differences.
    ranked = np.round(differences, 15)
    nonzero = ranked[ranked != 0]
    if not len(nonzero):
        return 1.0
    method = "exact"
    if len(np.unique(np.abs(nonzero))) < len(nonzero):
        # Rank ties require an exhaustive sign permutation with the observed ranks.
        method = PermutationMethod(n_resamples=2 ** len(nonzero), batch=1024)
    return float(wilcoxon(nonzero, alternative="greater", method=method).pvalue)


def paired_difference(
    df: pd.DataFrame,
    a_filter: _RunFilter,
    b_filter: _RunFilter,
    metric: str,
    key_cols: Sequence[str] = (_SEED, _NOISE, _FIELD_SET),
    *,
    infer: bool = True,
) -> pd.DataFrame:
    """Compare A minus B on matching seeds, with a t interval and optional exact inference.

    The one-sided Wilcoxon test and Holm adjustment apply only to the three
    hypothesis noise levels, separately for each field set. Incomplete seed
    pairs are excluded. Sample SD and the t interval require at least two pairs.
    """
    keys = list(key_cols)
    if not {_SEED, _NOISE, _FIELD_SET} <= set(keys):
        raise ValueError("Pairing keys must include seed, noise_level and field_set")
    columns = [*keys, metric]
    a = _select(df, a_filter).loc[:, columns].rename(columns={metric: "_a"})
    b = _select(df, b_filter).loc[:, columns].rename(columns={metric: "_b"})
    paired = a.merge(b, on=keys, validate="one_to_one").dropna(subset=["_a", "_b"])
    rows = []
    for (noise, field), group in paired.groupby([_NOISE, _FIELD_SET], sort=False, observed=True):
        deltas = (group["_a"] - group["_b"]).to_numpy(dtype=float)
        n = len(deltas)
        if group[_SEED].nunique() != n:
            raise ValueError("Expected one paired observation per seed, noise level and field set")
        mean = float(deltas.mean())
        std = float(deltas.std(ddof=1)) if n > 1 else np.nan
        margin = float(t.ppf(0.975, n - 1)) * std / sqrt(n) if n > 1 else np.nan
        p = _wilcoxon_greater(deltas) if infer and noise in HYPOTHESIS_NOISE_LEVELS else np.nan
        rows.append((noise, field, mean, std, mean - margin, mean + margin, int((deltas > 0).sum()), n, p))

    result = pd.DataFrame(
        rows, columns=(_NOISE, _FIELD_SET, "mean", "std", "ci_low", "ci_high", "wins", "n_seeds", "p_value")
    )
    result["p_holm"] = np.nan
    if infer:
        for _, group in result.groupby(_FIELD_SET, sort=False, observed=True):
            family = group.set_index(_NOISE)["p_value"].reindex(HYPOTHESIS_NOISE_LEVELS)
            adjusted = pd.Series(holm_adjust(family.to_numpy()), index=family.index)
            result.loc[group.index, "p_holm"] = group[_NOISE].map(adjusted)
    return result


def mean_ci95_half_width(x):
    x = np.asarray(x, float)
    if len(x) < 2 or np.isnan(x).any():
        return float("nan")
    if np.all(x == x[0]):
        return 0.0
    return float(t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / sqrt(len(x)))


def paired_effect(differences, *, rng_seed: int, bootstrap_draws: int):
    differences = np.asarray(differences, dtype=float)
    differences = differences[~np.isnan(differences)]
    if len(differences) == 0:
        return {"n": 0, "hodges_lehmann": None, "hl_ci95": [None, None],
                "rank_biserial": None, "cohens_dz": None}
    pairwise = (differences[:, None] + differences[None, :]) / 2.0
    hl = float(np.median(pairwise.ravel()))
    rng = np.random.default_rng(rng_seed)
    boot = []
    for _ in range(bootstrap_draws):
        sample = rng.choice(differences, size=len(differences), replace=True)
        pairwise_boot = (sample[:, None] + sample[None, :]) / 2.0
        boot.append(float(np.median(pairwise_boot.ravel())))
    ci = np.quantile(boot, [0.025, 0.975]).tolist()
    positive = np.sum(differences > 0)
    negative = np.sum(differences < 0)
    r = (positive - negative) / (positive + negative) if positive + negative else 0.0
    dz = float(differences.mean() / differences.std(ddof=1)) if len(differences) > 1 and differences.std(ddof=1) > 0 else 0.0
    return {"n": int(len(differences)), "hodges_lehmann": hl,
            "hl_ci95": [float(ci[0]), float(ci[1])],
            "rank_biserial": float(r), "cohens_dz": dz}


def paired_seed_differences(a: pd.DataFrame, b: pd.DataFrame, metric: str):
    if "seed" not in a or "seed" not in b:
        raise ValueError("paired comparison requires a seed column")
    a_seeds = set(a["seed"].tolist())
    b_seeds = set(b["seed"].tolist())
    if a_seeds != b_seeds:
        raise ValueError(f"paired seed sets do not match: {sorted(a_seeds)} != {sorted(b_seeds)}")
    merged = a.merge(b, on="seed", validate="one_to_one",
                     suffixes=("_standard", "_tuned"))
    x = merged[f"{metric}_standard"].to_numpy(dtype=float)
    y = merged[f"{metric}_tuned"].to_numpy(dtype=float)
    differences = y - x  # tuned - standard: positive means tuned is better
    differences = differences[differences != 0]
    return differences, len(merged)


def complete_seed_differences(baseline: pd.DataFrame, comparison: pd.DataFrame, metric: str) -> np.ndarray:
    """Return comparison minus baseline, including zero differences for matched seeds."""
    if baseline["seed"].duplicated().any() or comparison["seed"].duplicated().any():
        raise ValueError("Paired effects require one observation per seed")
    left = baseline.set_index("seed")[metric].sort_index()
    right = comparison.set_index("seed")[metric].sort_index()
    if left.empty or not left.index.equals(right.index):
        raise ValueError("Paired effects require nonempty matching seed sets")
    differences = (right - left).to_numpy(dtype=float)
    if not np.isfinite(differences).all():
        raise ValueError("Paired effects require finite complete observations")
    return differences


def matched_rank_biserial(differences: np.ndarray) -> float:
    """Contrast positive and negative rank sums, dropping zeros and averaging ties."""
    differences = np.asarray(differences, dtype=float)
    nonzero = differences[differences != 0]
    if not len(nonzero):
        return 0.0
    ranks = rankdata(np.abs(nonzero))
    return float(np.dot(ranks, np.sign(nonzero)) / ranks.sum())


def paired_bootstrap_summary(differences: np.ndarray, *, rng_seed: int, bootstrap_draws: int) -> dict:
    """Estimate paired mean and Walsh-median differences with percentile intervals."""
    values = np.asarray(differences, dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError("Paired bootstrap requires a nonempty vector of finite differences")
    if type(bootstrap_draws) is not int or bootstrap_draws < 1:
        raise ValueError("bootstrap_draws must be a positive integer")

    i, j = np.triu_indices(len(values))
    boot = np.random.default_rng(rng_seed).choice(values, size=(bootstrap_draws, len(values)), replace=True)
    means = boot.mean(axis=1)
    hl = np.median((boot[:, i] + boot[:, j]) / 2, axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    hl_low, hl_high = np.quantile(hl, [0.025, 0.975])
    mean = float(values.mean())
    std = values.std(ddof=1) if len(values) > 1 else 0.0
    return {"n_seeds": len(values), "mean_difference": mean, "ci_low": float(low), "ci_high": float(high),
            "hodges_lehmann": float(np.median((values[i] + values[j]) / 2)),
            "hl_ci_low": float(hl_low), "hl_ci_high": float(hl_high),
            "rank_biserial": matched_rank_biserial(values),
            "cohens_dz": mean / float(std) if std else (0.0 if mean == 0 else None)}
