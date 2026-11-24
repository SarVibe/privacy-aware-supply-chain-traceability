"""Choose configurations using paired validation observations."""

from dataclasses import dataclass

import pandas as pd

from src.common.evaluation.aggregation import aggregate_runs, complete_seed_differences, paired_bootstrap_summary
from src.rq2.collision_config import CollisionConfig


@dataclass(frozen=True)
class Selection:
    recommended: tuple[int, int]
    extreme: tuple[int, int]
    near_ties: tuple[tuple[int, int], ...]
    minimum_f1: float
    table: pd.DataFrame


def select_collision_config(validation: pd.DataFrame, cfg: CollisionConfig) -> Selection:
    """Rank seed-mean validation leakage subject to the validation F1 budget."""
    means = aggregate_runs(validation, ("l", "k"), ("attack_success", "f1"))
    means = means.rename(columns={"attack_success_mean": "validation_attack_success", "f1_mean": "validation_f1"})
    means = means.sort_values(["validation_attack_success", "validation_f1", "l", "k"],
                              ascending=[True, False, False, True]).reset_index(drop=True)
    reference = means.loc[(means["l"] == cfg.baseline[0]) & (means["k"] == cfg.baseline[1])].iloc[0]
    floor = float(reference["validation_f1"] - cfg.analysis.f1_budget)
    eligible = means.loc[means["validation_f1"] >= floor]
    winner = eligible.iloc[0]
    best = int(winner["l"]), int(winner["k"])
    extreme = int(means.iloc[0]["l"]), int(means.iloc[0]["k"])
    best_runs = validation.loc[(validation["l"] == best[0]) & (validation["k"] == best[1])]
    rows = []
    for row in means.itertuples(index=False):
        pair = row.l, row.k
        candidate = validation.loc[(validation["l"] == row.l) & (validation["k"] == row.k)]
        delta = complete_seed_differences(best_runs, candidate, "attack_success")
        effect = paired_bootstrap_summary(delta, rng_seed=cfg.analysis.seed, bootstrap_draws=cfg.analysis.bootstrap_draws)
        is_eligible = row.validation_f1 >= floor
        rows.append({
            "l": row.l, "k": row.k, "validation_attack_success": row.validation_attack_success,
            "validation_f1": row.validation_f1, "attack_gap_ci_low": effect["ci_low"],
            "attack_gap_ci_high": effect["ci_high"], "eligible": is_eligible,
            "recommended": pair == best, "extreme": pair == extreme,
            "near_tie": pair != best and is_eligible and effect["ci_low"] <= 0 <= effect["ci_high"],
        })
    table = pd.DataFrame(rows)
    near_ties = tuple((row.l, row.k) for row in table.loc[table["near_tie"]].itertuples(index=False))
    return Selection(best, extreme, near_ties, floor, table)
