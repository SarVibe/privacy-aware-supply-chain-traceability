"""E2.1-E2.7: the main (l, k) x noise x seed grid, plus the exact-hash baseline.

Examples
  python -m experiments.rq2.grid_runner --quick                          # tiny smoke run (~1 min)
  python -m experiments.rq2.grid_runner --seeds 10 --workers 4           # full grid, synthetic data
  python -m experiments.rq2.grid_runner --data data/Suppy_Chain_Shipment_Data.csv --column raw_item_description --seeds 10
  python -m experiments.rq2.grid_runner --composite --seeds 10
  python -m experiments.rq2.grid_runner --overlaps 0.5 0.2 --ls 1024 512 --ks 4 15 --out backend/app/results/rq2/raw/exp2_overlap.csv   # E2.7
"""
import argparse
import itertools
import time
from concurrent.futures import ProcessPoolExecutor

import pandas as pd
from pathlib import Path

from src.application_config import Config
from src.common.experiment_metadata import add_common_args, parse_standard, write_run_csv
from src.rq2.parameter_validation import validate_noise, validate_overlap, validate_n_records
from src.rq2.privacy_metrics import effective_noise
from src.rq2.experiment_config import DEFAULT_KS, DEFAULT_LS, DEFAULT_NOISES, DEFAULT_PAD, DEFAULT_Q
from src.rq2.rq2_dataset import (
    controlled_noise_dataset,
    apply_real_frequency_counts,
    load_dataset,
)
from src.rq2.privacy_pipeline import build_scenario, run_bloom, run_exact


def work(task):
    ds, seed, noise, overlap, n_records, ls, ks, q, noise_source, clean_path, noise_dir, composite_columns, frequency_data = task
    if noise_source == "files":
        ds = controlled_noise_dataset(
            clean_path=clean_path,
            noise_dir=noise_dir,
            noise_level=noise,
            seed=seed,
            n=ds.n,
            composite_columns=composite_columns,
        )
    if frequency_data:
        ds = apply_real_frequency_counts(ds, frequency_data, seed)
    scen = build_scenario(ds, seed, noise, overlap, n_records, q, DEFAULT_PAD)
    rows = [run_exact(ds, scen, q)]
    for l, k in itertools.product(ls, ks):
        if k <= l:
            rows.append(run_bloom(ds, scen, l, k, q, DEFAULT_PAD))
    return rows


def main():
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    ap.set_defaults(data=str(Config.MASTER_PRODUCTS_PATH))
    ap.add_argument("--noise-source", choices=["inline", "files"], default="files")
    ap.add_argument("--noise-dir", default=str(Config.DATA_GENERATED_DIR))
    ap.add_argument("--seed-values", type=int, nargs="+", default=None)
    ap.add_argument("--frequency-data", default=None,
                    help="raw CSV used only to preserve real entity frequencies for A2")
    ap.add_argument("--ls", type=int, nargs="+", default=list(DEFAULT_LS))
    ap.add_argument("--ks", type=int, nargs="+", default=list(DEFAULT_KS))
    ap.add_argument("--noises", type=float, nargs="+", default=list(DEFAULT_NOISES))
    ap.add_argument("--overlaps", type=float, nargs="+", default=[1.0])
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", default=str(Config.RQ2_RAW_DIR / "exp2_grid.csv"))
    ap.add_argument("--quick", action="store_true", help="3 seeds, 300 entities, reduced grid")
    a = ap.parse_args()
    for noise in a.noises:
        validate_noise(noise)
    for overlap in a.overlaps:
        validate_overlap(overlap)
    a.n_records = validate_n_records(a.n_records)
    try:
        sl, sk = parse_standard(a.standard)
    except ValueError as exc:
        ap.error(str(exc))
    if a.quick:
        a.seeds, a.n_entities, a.n_records = 3, 300, 1000
        a.ls, a.ks, a.noises = [1024, 512, 256], [4, 15, 30], [0.0, 0.15]

    composite_columns = (
        a.composite_columns
        if a.composite_columns is not None
        else ["dosage", "dosage_form", "pack_size"] if a.composite else None
    )
    if a.noise_source == "files":
        ds = controlled_noise_dataset(
            clean_path=a.data,
            noise_dir=a.noise_dir,
            noise_level=a.noises[0],
            seed=42,
            n=a.n_entities,
            composite_columns=composite_columns,
        )
    else:
        ds = load_dataset(a.data, a.column, a.n_entities, composite_columns=composite_columns)
    if a.frequency_data:
        ds = apply_real_frequency_counts(ds, a.frequency_data, a.seed_values[0] if a.seed_values else 42)
    if a.n_entities > ds.n:
        print(f"WARNING: requested n_entities={a.n_entities} exceeds available entities={ds.n}; using {ds.n}")
    if ds.n < 4:
        ap.error(f"dataset has only {ds.n} records; at least 4 are required")
    if not any(l == sl and k == sk for l in a.ls for k in a.ks):
        ap.error(f"standard configuration {sl}:{sk} is not present in the grid")
    print(f"dataset: {ds.source} entities={ds.n}")
    if a.seed_values is not None:
        seed_values = list(a.seed_values)
    elif a.noise_source == "files":
        seed_values = list(range(42, 57))
        if a.seeds < len(seed_values):
            seed_values = seed_values[:a.seeds]
    else:
        seed_values = list(range(a.seeds))
    tasks = [(ds, s, n, o, a.n_records, a.ls, a.ks, a.q, a.noise_source,
              a.data, a.noise_dir, composite_columns, a.frequency_data)
             for s in seed_values for n in a.noises for o in a.overlaps]
    t0, rows = time.time(), []
    if a.workers > 1:
        with ProcessPoolExecutor(a.workers) as ex:
            for i, r in enumerate(ex.map(work, tasks), 1):
                rows += r
                print(f"[{i}/{len(tasks)}] {time.time() - t0:.0f}s", flush=True)
    else:
        for i, t in enumerate(tasks, 1):
            rows += work(t)
            print(f"[{i}/{len(tasks)}] seed={t[1]} noise={t[2]} overlap={t[3]}  {time.time() - t0:.0f}s", flush=True)
    data_mode = "composite" if a.composite or a.composite_columns else "description"
    effective = []
    for seed in seed_values:
        for noise in a.noises:
            effective_ds = ds
            if a.noise_source == "files":
                effective_ds = controlled_noise_dataset(
                    clean_path=a.data,
                    noise_dir=a.noise_dir,
                    noise_level=noise,
                    seed=seed,
                    n=a.n_entities,
                    composite_columns=composite_columns,
                )
            scen = build_scenario(effective_ds, seed, noise, 1.0, a.n_records, a.q, DEFAULT_PAD)
            effective.append(effective_noise(effective_ds.norm, scen.b_norm))
    unchanged_fraction = (
        sum(item["unchanged_fraction"] for item in effective) / len(effective) if effective else None
    )
    average_edit_distance = (
        sum(item["average_normalized_edit_distance"] for item in effective) / len(effective) if effective else None
    )
    write_run_csv(pd.DataFrame(rows), a.out, q=a.q, pad=DEFAULT_PAD,
                  data_mode=data_mode, dataset_path=a.data,
                  nominal_noise_rates=[float(v) for v in a.noises],
                  nominal_noise=None,
                  unchanged_fraction=unchanged_fraction,
                  average_normalized_edit_distance=average_edit_distance)
    print(f"saved {len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    main()
