"""E2.8 (optional): collision tuning vs randomized-response DP, and the two combined.

For each chosen (l, k) configuration sweep eps (inf = no DP). Smaller eps = more bit flips.
"""
import argparse
import time

import pandas as pd

from src.config import Config
from src.rq2.config import DEFAULT_PAD, DEFAULT_Q
from src.rq2.data import load_dataset
from src.rq2.pipeline import build_scenario, run_bloom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(Config.RAW_DATA_PATH),
                    help="CSV dataset (default: the real shipment dataset)")
    ap.add_argument("--column", default="raw_item_description",
                    help="Primary text column; aliases raw_item_description and item description")
    ap.add_argument("--composite", action="store_true",
                    help="Combine description, dosage, dosage form, and pack/unit attributes")
    ap.add_argument("--composite-columns", nargs="+", default=None,
                    help="Optional explicit composite attribute column names")
    ap.add_argument("--n-entities", type=int, default=1000)
    ap.add_argument("--n-records", type=int, default=3000)
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--noise", type=float, default=0.05)
    ap.add_argument("--configs", nargs="+", default=["1024:4", "512:4"], help="l:k pairs, e.g. 1024:4 512:15")
    ap.add_argument("--eps", type=float, nargs="+", default=[2, 4, 8, 16, 32, 64, float("inf")])
    ap.add_argument("--out", default=str(Config.RQ2_RAW_DIR / "exp2_dp.csv"))
    a = ap.parse_args()

    composite_columns = (
        a.composite_columns
        if a.composite_columns is not None
        else ["dosage", "dosage_form", "pack_size"] if a.composite else None
    )
    ds = load_dataset(a.data, a.column, a.n_entities, composite_columns=composite_columns)
    cfgs = [tuple(int(x) for x in c.split(":")) for c in a.configs]
    rows, t0 = [], time.time()
    for seed in range(a.seeds):
        scen = build_scenario(ds, seed, a.noise, 1.0, a.n_records, DEFAULT_Q, DEFAULT_PAD)
        for (l, k) in cfgs:
            for eps in a.eps:
                rows.append(run_bloom(ds, scen, l, k, DEFAULT_Q, DEFAULT_PAD, eps=eps))
        print(f"seed {seed + 1}/{a.seeds} {time.time() - t0:.0f}s", flush=True)
    pd.DataFrame(rows).to_csv(a.out, index=False)
    print(f"saved {len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    main()
