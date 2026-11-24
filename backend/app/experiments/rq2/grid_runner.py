"""Deprecated legacy grid. Use experiments.rq2.collision_runner for new RQ2 studies."""

import argparse
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from src.common.config import all_fields_noise, load_config, positive_integer, unit_interval
from src.common.data.loader import BASE_DATASET_FILENAME
from src.common.experiment.io import write_csv
from src.common.experiment.runner import iter_grid
from src.common.experiment_metadata import write_run_csv
from src.common.linking.threshold import threshold_values
from src.common.paths import prepared_dir, results_dir
from src.rq2.privacy_metrics import effective_noise
from src.rq2.privacy_pipeline import build_scenario, run_bloom, run_exact
from src.rq2.rq2_dataset import load_research_dataset


def work(task):
    cfg, seed, noise, overlap, n_records, max_records, ls, ks, taus, ratio = task
    dataset = load_research_dataset(cfg, seed, noise, max_records=max_records)
    q = cfg.bloom.q
    scenario = build_scenario(dataset, seed, noise, overlap, n_records, q, dict_extra_ratio=ratio)
    rows = [run_exact(dataset, scenario, q)]
    for point in iter_grid({"l": ls, "k": ks}):
        rows.append(run_bloom(dataset, scenario, **point, q=q, taus=taus))
    return rows, effective_noise(dataset.norm, scenario.b_norm)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["reduced", "extended"], default="reduced")
    seed_args = parser.add_mutually_exclusive_group()
    seed_args.add_argument("--seeds", type=int, help="number of configured seeds")
    seed_args.add_argument("--seed-values", nargs="+", type=int)
    parser.add_argument("--ls", nargs="+", type=int)
    parser.add_argument("--ks", nargs="+", type=int)
    parser.add_argument("--noises", nargs="+", type=float)
    parser.add_argument("--overlaps", nargs="+", type=float)
    parser.add_argument("--tau-grid", type=float, nargs="+")
    parser.add_argument("--n-records", type=int, help="victim draws per scenario")
    parser.add_argument("--max-records", type=int, help="limit prepared records by whole entity groups")
    parser.add_argument("--dict-extra-ratio", type=float)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--noise-source", choices=["files"], default="files", help=argparse.SUPPRESS)
    parser.add_argument("--composite", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--quick", action="store_true", help="one seed and at most 200 prepared records")
    parser.add_argument("--all-fields", action="store_true", help="use the versioned all-field noise artifacts")
    args = parser.parse_args(argv)
    cfg = load_config("rq2" if args.profile == "reduced" else "rq2_extended")
    if args.all_fields:
        cfg = all_fields_noise(cfg)
    sweep = cfg.sweep
    if args.seeds is not None and not 1 <= args.seeds <= len(cfg.seeds):
        parser.error("--seeds is outside the number of configured prepared seeds")
    seeds = tuple(args.seed_values) if args.seed_values else cfg.seeds[:args.seeds]
    lengths = args.ls or sweep.lengths
    hashes = args.ks or sweep.hashes
    noises = args.noises or cfg.noise_levels
    overlaps = args.overlaps or [sweep.overlap]
    taus = tuple(args.tau_grid) if args.tau_grid else threshold_values(cfg.tau_grid)
    draws = args.n_records if args.n_records is not None else sweep.victim_draws
    ratio = args.dict_extra_ratio if args.dict_extra_ratio is not None else sweep.dict_extra_ratio
    out = args.out or results_dir(cfg, "rq2") / sweep.grid_csv
    if args.quick:
        seeds = seeds[:1]
        limit = sweep.max_quick_records
        args.max_records = limit if args.max_records is None else min(limit, args.max_records)
        draws = min(limit, draws)
    if not seeds or len(set(seeds)) != len(seeds) or not set(seeds) <= set(cfg.seeds):
        parser.error("Choose unique seed values from the configured prepared seeds")
    if not set(noises) <= set(load_config("rq1").noise_levels):
        parser.error("Choose noise levels available in the prepared dataset")
    try:
        positive_integer(args.workers, "workers")
        positive_integer(draws, "n-records")
        for name, axis in (("l", lengths), ("k", hashes)):
            for value in axis:
                positive_integer(value, name)
        for tau in taus:
            unit_interval(tau, "tau")
        for name, axis in (("l", lengths), ("k", hashes), ("noise", noises), ("overlap", overlaps), ("tau", taus)):
            if len(set(axis)) != len(axis):
                raise ValueError(f"{name} values must be unique")
    except ValueError as exc:
        parser.error(str(exc))
    tasks = [
        (cfg, seed, noise, overlap, draws, args.max_records, lengths, hashes, taus, ratio)
        for seed in seeds for noise in noises for overlap in overlaps
    ]
    started = time.monotonic()
    if args.workers > 1:
        with ProcessPoolExecutor(args.workers) as executor:
            runs = list(executor.map(work, tasks))
    else:
        runs = [work(task) for task in tasks]
    rows = pd.DataFrame(row for scenarios, _ in runs for row in scenarios)
    effective = [metrics for _, metrics in runs]
    candidates = rows.loc[(rows["method"] == "bloom") & rows["feasible_01"].eq(True)]
    if not candidates.empty:
        means = candidates.groupby(["l", "k"], as_index=False)[
            ["precision", "recall", "f1", "cross_party_fpr", "fill", "load"]
        ].mean()
        optimal = means.sort_values(["f1", "cross_party_fpr"], ascending=[False, True], kind="stable").head(1)
        write_csv(optimal, out.with_name(f"{out.stem}_optimal_configuration.csv"))
    write_run_csv(
        rows, out, cfg=cfg, data_mode="composite", tau_grid=taus,
        dataset_path=str(prepared_dir(cfg) / BASE_DATASET_FILENAME),
        nominal_noise_rates=list(noises),
        analysis_scope={"profile": args.profile, "seed_values": list(seeds), "lengths": list(lengths),
                        "hashes": list(hashes), "overlaps": list(overlaps), "victim_draws": draws,
                        "max_records": args.max_records, "noisy_artifacts": cfg.paths.noisy,
                        "primary_metric": "unordered_cluster_pairs", "secondary_metric": "cross_party_pairs"},
        unchanged_fraction=sum(m["unchanged_fraction"] for m in effective) / len(effective),
        average_normalized_edit_distance=sum(m["average_normalized_edit_distance"] for m in effective) / len(effective),
    )
    print(f"saved {len(rows)} rows -> {out} ({time.monotonic() - started:.1f}s)")


if __name__ == "__main__":
    main()
