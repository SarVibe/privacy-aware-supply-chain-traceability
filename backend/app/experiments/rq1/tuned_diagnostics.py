"""Tune on the saved validation groups and evaluate the held-out groups."""

from itertools import groupby

import pandas as pd

from experiments.rq1.diagnostic_inputs import diagnostic_cases
from experiments.rq1.overmerge_diagnostics import DEFAULT_OUTPUT, component_profile
from src.common.config import load_config
from src.common.evaluation.aggregation import mean_ci95_half_width
from src.common.evaluation.metrics import evaluate_clusters
from src.common.experiment.io import write_csv
from src.common.linking.bloom import BloomLinker
from src.common.linking.threshold import select_per_noise_tau, select_single_tau, threshold_values, tune_tau

MEASURES = (
    "tau", "precision", "recall", "f1", "clusters", "largest_component",
    "largest_component_true_entities", "predicted_pairs", "top_3_pair_share",
)


def summarize_tuned_rows(test_rows):
    summary = []
    keys = ["dataset", "variant", "policy", "noise"]
    for dimension, group in test_rows.groupby(keys, sort=True):
        row = dict(zip(keys, dimension, strict=True))
        row["n_seeds"] = group.seed.nunique()
        for measure in MEASURES:
            values = group[measure]
            mean, margin = float(values.mean()), mean_ci95_half_width(values)
            row.update({
                f"{measure}_mean": mean, f"{measure}_ci95_low": mean - margin,
                f"{measure}_ci95_high": mean + margin,
            })
        summary.append(row)
    return pd.DataFrame(summary)


def tuned_evaluations(cfg, variants):
    grid = threshold_values(cfg.tau_grid)
    rid, eid = cfg.columns.record_id, cfg.columns.entity_id
    test_rows, validation_rows = [], []
    for (dataset, seed), run in groupby(diagnostic_cases(cfg), key=lambda case: (case.dataset, case.seed)):
        cases = list(run)
        val = {case.noise: case.validation for case in cases}
        for variant, field_set in variants:
            metrics = tune_tau(val, grid, {"cfg": cfg, "field_set": field_set})
            validation_rows.append(metrics.assign(dataset=dataset, seed=seed, variant=variant))
            single, per_level = select_single_tau(metrics), select_per_noise_tau(metrics)
            linker = BloomLinker("bloom", field_set, min(grid), cfg)
            for case in cases:
                frame = case.test
                truth = frame.set_index(rid)[eid]
                prepared = linker.prepare(frame.drop(columns=eid), min(single, per_level[case.noise]))
                for policy, tau in (("single", single), ("per_noise", per_level[case.noise])):
                    labels = prepared.labels_at(tau)
                    component_stats, _ = component_profile(truth, labels)
                    test_rows.append({
                        "dataset": dataset, "seed": seed, "variant": variant, "field_set": field_set,
                        "noise": case.noise, "policy": policy, "tau": tau,
                        "n_validation_records": len(case.validation), **evaluate_clusters(truth, labels),
                        **component_stats,
                    })
    return pd.DataFrame(test_rows), pd.concat(validation_rows, ignore_index=True)


def write_tuned_tables(test_rows, validation_rows, prefix):
    write_csv(test_rows, DEFAULT_OUTPUT / f"{prefix}_test.csv")
    write_csv(validation_rows, DEFAULT_OUTPUT / f"{prefix}_validation.csv")
    write_csv(summarize_tuned_rows(test_rows), DEFAULT_OUTPUT / f"{prefix}_summary.csv")


def main():
    cfg = load_config("rq1_diagnostics")
    test_rows, validation_rows = tuned_evaluations(cfg, [("V0", "composite")])
    write_tuned_tables(test_rows, validation_rows, "tuned_composite")
    print(f"Saved {len(test_rows)} held-out evaluations to {DEFAULT_OUTPUT}")


if __name__ == "__main__":
    main()
