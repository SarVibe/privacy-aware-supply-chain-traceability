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

import numpy as np
import pandas as pd
from pathlib import Path

from src.application_config import Config
from src.application_config import EXPERIMENT_CONFIG
from src.common.experiment_metadata import add_common_args, parse_standard, write_run_csv
from src.rq2.parameter_validation import (
    validate_noise,
    validate_overlap,
    validate_n_records,
    validate_bloom_parameters,
)
from src.rq2.parameter_validation import validate_tau
from src.rq2.privacy_metrics import effective_noise
from src.rq2.experiment_config import DEFAULT_KS, DEFAULT_LS, DEFAULT_NOISES, DEFAULT_PAD, DEFAULT_Q
from src.rq2.rq2_dataset import (
    controlled_noise_dataset,
    apply_real_frequency_counts,
    load_dataset,
)
from src.rq2.privacy_pipeline import build_scenario, run_bloom, run_exact


def work(task):
    ds, seed, noise, overlap, n_records, ls, ks, q, noise_source, clean_path, noise_dir, composite_columns, frequency_data, tau_values, dict_extra_ratio = task
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
    scen = build_scenario(ds, seed, noise, overlap, n_records, q, DEFAULT_PAD, dict_extra_ratio)
    rows = [run_exact(ds, scen, q)]
    for l, k in itertools.product(ls, ks):
        if k <= l:
            try:
                validate_bloom_parameters(l, k)
            except ValueError:
                pass  # validation is best-effort; we still run with expanded ranges
            row = run_bloom(ds, scen, l, k, q, DEFAULT_PAD, taus=tau_values)
            rows.append(row)
    return rows


def print_entity_weights(ds, context):
    if ds.frequency_counts is not None:
        source = "shipment row counts"
    elif ds.source.startswith("synthetic("):
        source = "Zipf"
    else:
        source = "master entity row counts"
    weights = ds.weights
    print(f"Entity weights ({context}, {source}): min={weights.min():.6g}, "
          f"median={np.median(weights):.6g}, max={weights.max():.6g}, "
          f"distinct={np.unique(weights).size}, top-10 share={np.sort(weights)[-10:].sum():.6%}")


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
    ap.add_argument("--dict-extra-ratio", type=float, default=5.0,
                    help="distractor dictionary entries per sampled entity")
    ap.add_argument("--tau-grid", type=float, nargs="+", default=None)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", default=str(Config.RQ2_RAW_DIR / "exp2_grid.csv"))
    ap.add_argument("--quick", action="store_true", help="3 seeds, 300 entities, reduced grid")
    a = ap.parse_args()
    for noise in a.noises:
        validate_noise(noise)
    for overlap in a.overlaps:
        validate_overlap(overlap)
    a.n_records = validate_n_records(a.n_records)
    tau_values = list(a.tau_grid or EXPERIMENT_CONFIG.tau_grid)
    for tau in tau_values:
        validate_tau(tau)
    try:
        sl, sk = parse_standard(a.standard)
    except ValueError as exc:
        ap.error(str(exc))
    if a.quick:
        a.seeds, a.n_entities, a.n_records = 3, 300, 1000
        a.ls, a.ks, a.noises = [1024, 512, 256], [4, 15, 30], [0.0, 0.15]

    a.ls = [l for l in a.ls if 128 <= l <= 2048]
    a.ks = [k for k in a.ks if 2 <= k <= 50]
    if not a.ls:
        ap.error("No l values remain within [128, 2048]")
    if not a.ks:
        ap.error("No k values remain within [2, 50]")

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
    if a.noise_source == "inline":
        print_entity_weights(ds, "all seeds and noise levels")
    if a.seed_values is not None:
        seed_values = list(a.seed_values)
    elif a.noise_source == "files":
        seed_values = list(range(42, 57))
        if a.seeds < len(seed_values):
            seed_values = seed_values[:a.seeds]
        elif a.seeds > len(seed_values) and a.seed_values is None:
            ap.error(
                "controlled-noise mode has only 15 generated seeds (42-56); "
                "generate the requested noise files or use --noise-source inline"
            )
    else:
        seed_values = list(range(a.seeds))
    tasks = [(ds, s, n, o, a.n_records, a.ls, a.ks, a.q, a.noise_source,
          a.data, a.noise_dir, composite_columns, a.frequency_data, tuple(tau_values),
          a.dict_extra_ratio)
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
                if a.frequency_data:
                    effective_ds = apply_real_frequency_counts(effective_ds, a.frequency_data, seed)
                print_entity_weights(effective_ds, f"seed={seed}, noise={noise}")
            scen = build_scenario(effective_ds, seed, noise, 1.0, a.n_records, a.q, DEFAULT_PAD)
            effective.append(effective_noise(effective_ds.norm, scen.b_norm))
    unchanged_fraction = (
        sum(item["unchanged_fraction"] for item in effective) / len(effective) if effective else None
    )
    average_edit_distance = (
        sum(item["average_normalized_edit_distance"] for item in effective) / len(effective) if effective else None
    )
    result_df = pd.DataFrame(rows)
    eligible = result_df[
        (result_df["method"] == "bloom")
        & (result_df["f1_unc"].notna() if "f1_unc" in result_df.columns else result_df["fpr"].notna())
        & (result_df.get("feasible_01", False) if "feasible_01" in result_df.columns else (result_df["fpr"] <= 0.01))
    ]
    if not eligible.empty:
        f1_col = "f1_unc" if "f1_unc" in eligible.columns else "f1"
        eligible_mean = eligible.groupby(["l", "k", "tau"], as_index=False)[
            ["precision", "recall", f1_col, "fpr", "fill", "load"]
        ].mean()
        optimal = eligible_mean.sort_values(
            [f1_col, "fpr"],
            ascending=[False, True],
            kind="stable",
        ).iloc[0]
        optimal_path = Path(a.out).with_name("optimal_configuration.csv")
        optimal_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([optimal]).to_csv(optimal_path, index=False)
        print(f"optimal configuration -> {optimal_path}")
    write_run_csv(result_df, a.out, q=a.q, pad=DEFAULT_PAD,
                  data_mode=data_mode, dataset_path=a.data,
                  nominal_noise_rates=[float(v) for v in a.noises],
                  nominal_noise=None,
                  unchanged_fraction=unchanged_fraction,
                  average_normalized_edit_distance=average_edit_distance)
    print(f"saved {len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    main()
