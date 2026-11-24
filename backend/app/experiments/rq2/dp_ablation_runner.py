"""E2.8 (optional): collision tuning vs randomized-response DP, and the two combined.

For each chosen (l, k) configuration sweep eps (inf = no DP). Smaller eps = more bit flips.
"""
import argparse
import time

import pandas as pd

from src.application_config import Config
from src.common.experiment_metadata import add_common_args, write_run_csv
from src.rq2.experiment_config import DEFAULT_PAD, DEFAULT_Q
from src.rq2.parameter_validation import validate_eps, validate_noise, validate_n_records
from src.rq2.rq2_dataset import (
    apply_real_frequency_counts,
    controlled_noise_dataset,
    load_dataset,
)
from src.rq2.privacy_pipeline import build_scenario, run_bloom


def main():
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    ap.set_defaults(data=str(Config.MASTER_PRODUCTS_PATH))
    ap.add_argument("--noise-source", choices=["inline", "files"], default="files")
    ap.add_argument("--noise-dir", default=str(Config.DATA_GENERATED_DIR))
    ap.add_argument("--seed-values", type=int, nargs="+", default=None)
    ap.add_argument("--frequency-data", default=None,
                    help="raw CSV used only to preserve real entity frequencies for A2")
    ap.add_argument("--noise", type=float, default=0.05)
    ap.add_argument("--configs", nargs="+",
                    default=["1024:4", "512:15", "256:8", "256:30"],
                    help="l:k pairs, e.g. 1024:4 512:15")
    ap.add_argument("--eps", type=float, nargs="+", default=[2, 4, 8, 16, 32, 64, float("inf")])
    ap.add_argument("--out", default=str(Config.RQ2_RAW_DIR / "exp2_dp.csv"))
    a = ap.parse_args()
    a.noise = validate_noise(a.noise)
    a.n_records = validate_n_records(a.n_records)
    a.eps = [validate_eps(value) for value in a.eps]

    composite_columns = (
        a.composite_columns
        if a.composite_columns is not None
        else ["dosage", "dosage_form", "pack_size"] if a.composite else None
    )
    if a.noise_source == "files":
        ds = controlled_noise_dataset(
            clean_path=a.data,
            noise_dir=a.noise_dir,
            noise_level=a.noise,
            seed=42,
            n=a.n_entities,
            composite_columns=composite_columns,
        )
    else:
        ds = load_dataset(a.data, a.column, a.n_entities, composite_columns=composite_columns)
    if a.frequency_data:
        ds = apply_real_frequency_counts(ds, a.frequency_data, a.seed_values[0] if a.seed_values else 42)
    cfgs = [tuple(int(x) for x in c.split(":")) for c in a.configs]
    rows, t0 = [], time.time()
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
        seed_values = list(range(a.n_selection, a.seeds))
    for seed in seed_values:
        if a.noise_source == "files":
            ds = controlled_noise_dataset(
                clean_path=a.data,
                noise_dir=a.noise_dir,
                noise_level=a.noise,
                seed=seed,
                n=a.n_entities,
                composite_columns=composite_columns,
            )
        if a.frequency_data:
            ds = apply_real_frequency_counts(ds, a.frequency_data, seed)
        scen = build_scenario(ds, seed, a.noise, 1.0, a.n_records, DEFAULT_Q)
        for (l, k) in cfgs:
            for eps in a.eps:
                rows.append(run_bloom(ds, scen, l, k, DEFAULT_Q, eps=eps))
        print(f"seed {seed + 1}/{a.seeds} {time.time() - t0:.0f}s", flush=True)
    data_mode = "composite" if a.composite or a.composite_columns else "description"
    write_run_csv(pd.DataFrame(rows), a.out, q=DEFAULT_Q, pad=DEFAULT_PAD,
                  data_mode=data_mode, dataset_path=a.data)
    print(f"saved {len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    main()
