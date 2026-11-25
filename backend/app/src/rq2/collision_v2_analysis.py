"""Paired validation selection and descriptive inference for frozen v2 endpoints."""

from math import log

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.common.evaluation.aggregation import aggregate_runs, complete_seed_differences, paired_bootstrap_summary
from src.rq2.collision_privacy import fingerprint_collision_proxy
from src.rq2.collision_v2_artifacts import CROSS, GROUP, MEASURES

PRECISION = "e2_precision_mean"
FALSE = "e2_false_candidates"
AMBIGUITY = "ambiguity_mean"
EXCESS = "excess_matched"


def select_v2_validation(validation: pd.DataFrame, cfg):
    means = aggregate_runs(validation, ("l", "k"), (PRECISION, "f1")).rename(
        columns={f"{PRECISION}_mean": "validation_e2_precision", "f1_mean": "validation_f1"}
    ).sort_values(["validation_e2_precision", "validation_f1", "l", "k"], ascending=[True, False, False, True])
    standard = _v2_cell(means, cfg.baseline).iloc[0]
    floor = float(standard["validation_f1"] - cfg.analysis.f1_budget)
    means["eligible"] = means["validation_f1"] >= floor
    first = means.loc[means["eligible"]].iloc[0]
    recommended = int(first["l"]), int(first["k"])
    extreme = int(means.iloc[0]["l"]), int(means.iloc[0]["k"])
    winner = _v2_cell(validation, recommended)
    rows = []
    for row in means.itertuples(index=False):
        pair = row.l, row.k
        effect = _effect(winner, _v2_cell(validation, pair), PRECISION, cfg)
        rows.append({"l": row.l, "k": row.k, "validation_f1": row.validation_f1,
                     "validation_e2_precision": row.validation_e2_precision,
                     "validation_gap_ci_low": effect["ci_low"], "validation_gap_ci_high": effect["ci_high"],
                     "eligible": row.eligible, "recommended": pair == recommended, "extreme": pair == extreme,
                     "near_tie": row.eligible and pair != recommended and effect["ci_low"] <= 0 <= effect["ci_high"]})
    return recommended, extreme, floor, pd.DataFrame(rows)


def _v2_cell(rows, pair):
    return rows.loc[rows["l"].eq(pair[0]) & rows["k"].eq(pair[1])]


def _effect(baseline, comparison, metric, cfg):
    return paired_bootstrap_summary(complete_seed_differences(baseline, comparison, metric),
                                    rng_seed=cfg.analysis.seed, bootstrap_draws=cfg.analysis.bootstrap_draws)


def _analytical(aggregate):
    rows = []
    for row in aggregate.itertuples(index=False):
        q_mean, universe = row.q_mean_mean, row.universe_size_mean
        proxy = fingerprint_collision_proxy(q_mean, row.l, row.k)
        rows.append(dict(variant=row.variant, noise=row.noise, l=row.l, k=row.k, q_mean=q_mean, universe_size=universe,
                         fill=row.fill_mean, fill_finite=row.fill_finite_mean, fill_exponential=row.fill_exponential_mean,
                         f=proxy, u_times_f=universe * proxy, k_opt=row.l * log(2) / q_mean,
                         false_candidates_finite=row.false_candidates_finite_mean,
                         e2_false_candidates=row.e2_false_candidates_mean))
    return pd.DataFrame(rows)


def _trends_v2(primary):
    rows = []

    def _append(hypothesis, scope, group, predictor, outcomes):
        for outcome in outcomes:
            values = group[[predictor, outcome]].dropna()
            rho = spearmanr(values[predictor], values[outcome]).statistic if (values.nunique() > 1).all() else np.nan
            rows.append(dict(hypothesis=hypothesis, scope=scope, predictor=predictor, outcome=outcome,
                             n_observations=len(values), spearman_rho=rho))

    for k, group in primary.groupby("k"):
        _append("H1'-a", f"k={k}", group, "l", (PRECISION, FALSE, AMBIGUITY))
        _append("H1'-b", f"k={k}", group, "l", (EXCESS,))
        _append("H1'-c", f"k={k}", group, "l", ("f1", "pr_auc"))
    for length, group in primary.groupby("l"):
        _append("H2'-a", f"l={length}", group, "k", ("fill",))
    _append("H2'-c", "fill>0.5", primary.loc[primary["fill"] > 0.5], "fill", ("f1",))
    _append("H2'-c", "fill<=0.5", primary.loc[primary["fill"] <= 0.5], "fill", ("f1",))
    return pd.DataFrame(rows)


def _hypothesis_verdicts(analytical, points, means, trends, effects, h3, cfg):
    rows = []

    def _record(hypothesis, scope, verdict, evidence):
        rows.append(dict(hypothesis=hypothesis, scope=scope, verdict=verdict, evidence=evidence))

    def _verdict(count, total):
        return "supported" if count == total else "partially supported" if count else "not supported"

    def _strict(series, direction):
        return bool((np.diff(series) * direction > 0).all())

    length_pass = []
    for k, grid in means.groupby("k"):
        grid = grid.sort_values("l")
        predicted = ((PRECISION, 1), (FALSE, -1), (AMBIGUITY, -1))
        flags = [_strict(grid[f"{metric}_mean"], direction) for metric, direction in predicted]
        if all(flags):
            length_pass.append(int(k))
        _record("H1'-a", f"k={k}", _verdict(sum(flags), 3),
                f"Strict directions in order E2 precision, false candidates, ambiguity: {flags}.")
        cluster, ap = (_strict(grid[f"{metric}_mean"], 1) for metric in ("f1", "pr_auc"))
        _record("H1'-c", f"k={k}", _verdict(int(cluster) + int(ap), 2),
                f"Strict F1 direction: {cluster}. Strict average precision direction: {ap}.")
    k_count = means["k"].nunique()
    count = len(length_pass)
    _record("H1'-a", "overall", "supported" if count == k_count else "partially supported" if count >= 2 else "not supported",
            f"All three mean trends held at {count} of {k_count} hash counts: {length_pass}.")
    violations = effects.loc[(effects["metric"] == EXCESS) & (effects["l"] < cfg.baseline[0]) & (effects["ci_low"] > 0)]
    cells = [(r.l, r.k) for r in violations.itertuples(index=False)]
    _record("H1'-b", "smaller lengths vs Baseline 2", "not supported" if cells else "supported",
            f"Smaller cells with a wholly positive paired matched-excess interval: {cells or 'none'}.")
    fill_pass = []
    for length, group in analytical.groupby("l"):
        group = group.sort_values("k").reset_index(drop=True)
        increasing = _strict(group["fill"], 1)
        fill_pass.append(increasing)
        _record("H2'-a", f"l={length}", _verdict(int(increasing), 1),
                f"Mean fill increased at every tested step: {increasing}.")
        values = group[FALSE]
        minimum = int(values.idxmin())
        observed_k = int(group.loc[minimum, "k"])
        predicted_k = int(group.loc[group["f"].idxmin(), "k"])
        shape = (0 < minimum < len(group) - 1 and _strict(values.iloc[:minimum + 1], -1)
                 and _strict(values.iloc[minimum:], 1))
        optimum = group["k_opt"].mean()
        _record("H2'-b", f"l={length}", _verdict(int(shape) + int(observed_k == predicted_k), 2),
                f"Observed argmin k={observed_k}; continuous k_opt={optimum:.2f}; analytical grid argmin k={predicted_k}. "
                f"Both sides of a strict interior U were observed: {shape}.")
    _record("H2'-a", "overall", _verdict(sum(fill_pass), len(fill_pass)),
            f"Strict growth in mean fill held at {sum(fill_pass)} of {len(fill_pass)} lengths.")
    fill_trend = trends.loc[trends["hypothesis"].eq("H2'-c")].set_index("scope")["spearman_rho"]
    high, low = fill_trend["fill>0.5"], fill_trend["fill<=0.5"]
    _record("H2'-c", "pooled", _verdict(int(high < 0) + int(high < 0 and abs(high) > abs(low)), 2),
            f"Descriptive rho above 0.5 = {high:.3f}, at or below 0.5 = {low:.3f}.")
    qualifying = int(h3["qualifies"].sum())
    _record("H3'", "held-out", _verdict(int(qualifying > 0), 1),
            f"{qualifying} of {len(points) - 1} non-baseline cells met both prespecified mean criteria.")
    return pd.DataFrame(rows)


def compute_v2_analysis(per_run, selection, cfg):
    summary = aggregate_runs(per_run, GROUP, MEASURES)
    is_primary = per_run["variant"].eq("description") & per_run["noise"].eq(cfg.primary_noise)
    primary = per_run.loc[is_primary]
    means = summary.loc[summary["variant"].eq("description") & summary["noise"].eq(cfg.primary_noise)]
    points = means[["l", "k", "f1_mean", f"{PRECISION}_mean"]].rename(
        columns={"f1_mean": "f1", f"{PRECISION}_mean": PRECISION}
    ).merge(selection, on=["l", "k"], validate="one_to_one")
    points["pareto"] = [
        not ((points[PRECISION] <= cell.e2_precision_mean) & (points["f1"] >= cell.f1)
             & ((points[PRECISION] < cell.e2_precision_mean) | (points["f1"] > cell.f1))).any()
        for cell in points.itertuples(index=False)
    ]
    baseline = _v2_cell(primary, cfg.baseline)
    baseline_precision = baseline[PRECISION].mean()
    effect_rows, h3_rows = [], []
    for (l, k), rows in primary.groupby(["l", "k"]):
        if (l, k) == cfg.baseline:
            continue
        effects = {m: _effect(baseline, rows, m, cfg)
                   for m in ("f1", "pr_auc", "direct_f1", "hit", EXCESS, "lift_matched", PRECISION, FALSE)}
        effect_rows.extend({"l": l, "k": k, "metric": m, **effect} for m, effect in effects.items())
        reduction = 1 - rows[PRECISION].mean() / baseline_precision
        f1 = effects["f1"]
        h3_rows.append(dict(l=l, k=k, relative_reduction=reduction, f1_difference=f1["mean_difference"],
                            ci_low=f1["ci_low"], ci_high=f1["ci_high"],
                            qualifies=reduction >= cfg.analysis.h3_relative_reduction
                            and f1["mean_difference"] >= -cfg.analysis.f1_budget))
    effects, h3 = pd.DataFrame(effect_rows), pd.DataFrame(h3_rows)
    analytical = _analytical(summary)
    trends = _trends_v2(primary)
    primary_analytical = analytical.loc[analytical["variant"].eq("description") & analytical["noise"].eq(cfg.primary_noise)]
    hypotheses = _hypothesis_verdicts(primary_analytical, points, means, trends, effects, h3, cfg)
    roles = points.loc[points["recommended"] | points["extreme"], ["l", "k"]]
    keep = {tuple(pair) for pair in roles.to_numpy()} | {cfg.baseline}
    cross = summary.loc[[(l, k) in keep for l, k in zip(summary["l"], summary["k"], strict=True)]].copy()
    standard = _v2_cell(cross, cfg.baseline).set_index(["variant", "noise"])
    for metric in CROSS:
        cross[f"{metric}_delta_vs_baseline"] = cross[f"{metric}_mean"] - [
            standard.loc[(row.variant, row.noise), f"{metric}_mean"] for row in cross.itertuples(index=False)
        ]
    cross = cross.loc[:, [*GROUP, "n_seeds",
                          *(f"{metric}_{suffix}" for metric in CROSS for suffix in ("mean", "std", "delta_vs_baseline"))]]
    return dict(aggregated=summary, analytical=analytical, pareto=points, paired_effects=effects,
                h3=h3, trends=trends, hypotheses=hypotheses, cross_check=cross)
