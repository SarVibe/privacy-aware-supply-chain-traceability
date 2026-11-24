"""Sweep Bloom parameters on the prepared RQ1 records."""

import argparse
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from src.common.config import load_config
from src.common.data.loader import BASE_DATASET_FILENAME
from src.common.experiment.io import write_csv
from src.common.experiment.runner import iter_grid
from src.common.experiment_metadata import write_run_csv
from src.common.paths import prepared_dir, results_dir
from src.rq2.experiment_config import DEFAULT_KS, DEFAULT_LS, DEFAULT_NOISES, TAU_GRID
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
    cfg = load_config("rq1")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=len(cfg.seeds))
    parser.add_argument("--seed-values", nargs="+", type=int)
    parser.add_argument("--ls", nargs="+", type=int, default=DEFAULT_LS)
    parser.add_argument("--ks", nargs="+", type=int, default=DEFAULT_KS)
    parser.add_argument("--noises", nargs="+", type=float, default=DEFAULT_NOISES)
    parser.add_argument("--overlaps", nargs="+", type=float, default=[1.0])
    parser.add_argument("--tau-grid", type=float, nargs="+", default=TAU_GRID)
    parser.add_argument("--n-records", type=int, default=3000, help="victim draws per scenario")
    parser.add_argument("--max-records", type=int, help="limit prepared records by whole entity groups")
    parser.add_argument("--dict-extra-ratio", type=float, default=5.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", type=Path, default=results_dir(cfg, "rq2") / "raw" / "exp2_grid.csv")
    parser.add_argument("--noise-source", choices=["files"], default="files", help=argparse.SUPPRESS)
    parser.add_argument("--composite", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--quick", action="store_true", help="one seed and at most 200 prepared records")
    parser.add_argument("--all-fields", action="store_true", help="use the versioned all-field noise artifacts")
    args = parser.parse_args(argv)
    if args.all_fields:
        cfg = load_config("rq1_all_fields")
    seeds = tuple(args.seed_values) if args.seed_values is not None else cfg.seeds[:args.seeds]
    if args.quick:
        seeds = seeds[:1]
        args.max_records = min(200, args.max_records or 200)
        args.n_records = min(200, args.n_records)
    if not seeds or len(set(seeds)) != len(seeds) or not set(seeds) <= set(cfg.seeds):
        parser.error("Choose unique seed values from the configured prepared seeds")
    if not set(args.noises) <= set(cfg.noise_levels):
        parser.error("Choose noise levels available in the prepared dataset")
    if args.workers < 1:
        parser.error("--workers must be positive")
    tasks = [
        (cfg, seed, noise, overlap, args.n_records, args.max_records, args.ls, args.ks,
         tuple(args.tau_grid), args.dict_extra_ratio)
        for seed in seeds for noise in args.noises for overlap in args.overlaps
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
        write_csv(optimal, args.out.with_name("optimal_configuration.csv"))
    write_run_csv(
        rows, args.out, q=cfg.bloom.q, pad=True, data_mode="composite",
        dataset_path=str(prepared_dir(cfg) / BASE_DATASET_FILENAME),
        nominal_noise_rates=list(args.noises),
        unchanged_fraction=sum(m["unchanged_fraction"] for m in effective) / len(effective),
        average_normalized_edit_distance=sum(m["average_normalized_edit_distance"] for m in effective) / len(effective),
    )
    print(f"saved {len(rows)} rows -> {args.out} ({time.monotonic() - started:.1f}s)")


if __name__ == "__main__":
    main()
