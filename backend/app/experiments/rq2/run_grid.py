"""E2.1-E2.7: the main (l, k) x noise x seed grid, plus the exact-hash baseline.

Examples
  python -m experiments.rq2.run_grid --quick                          # tiny smoke run (~1 min)
  python -m experiments.rq2.run_grid --seeds 10 --workers 4           # full grid, synthetic data
  python -m experiments.rq2.run_grid --data data/Suppy_Chain_Shipment_Data.csv --column raw_item_description --seeds 10
  python -m experiments.rq2.run_grid --composite --seeds 10
  python -m experiments.rq2.run_grid --overlaps 0.5 0.2 --ls 1024 512 --ks 4 15 --out backend/app/results/rq2/raw/exp2_overlap.csv   # E2.7
"""
import argparse
import itertools
import time
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from src.config import Config
from src.rq2.config import DEFAULT_KS, DEFAULT_LS, DEFAULT_NOISES, DEFAULT_PAD, DEFAULT_Q
from src.rq2.data import load_dataset
from src.rq2.pipeline import build_scenario, run_bloom, run_exact


def work(task):
    ds, seed, noise, overlap, n_records, ls, ks, q = task
    scen = build_scenario(ds, seed, noise, overlap, n_records, q, DEFAULT_PAD)
    rows = [run_exact(ds, scen, q)]
    for l, k in itertools.product(ls, ks):
        if k <= l:
            rows.append(run_bloom(ds, scen, l, k, q, DEFAULT_PAD))
    return rows


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
    ap.add_argument("--ls", type=int, nargs="+", default=list(DEFAULT_LS))
    ap.add_argument("--ks", type=int, nargs="+", default=list(DEFAULT_KS))
    ap.add_argument("--noises", type=float, nargs="+", default=list(DEFAULT_NOISES))
    ap.add_argument("--overlaps", type=float, nargs="+", default=[1.0])
    ap.add_argument("--q", type=int, default=DEFAULT_Q)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", default=str(Config.RQ2_RAW_DIR / "exp2_grid.csv"))
    ap.add_argument("--quick", action="store_true", help="3 seeds, 300 entities, reduced grid")
    a = ap.parse_args()
    if a.quick:
        a.seeds, a.n_entities, a.n_records = 3, 300, 1000
        a.ls, a.ks, a.noises = [1024, 512, 256], [4, 15, 30], [0.0, 0.15]

    composite_columns = (
        a.composite_columns
        if a.composite_columns is not None
        else ["dosage", "dosage_form", "pack_size"] if a.composite else None
    )
    ds = load_dataset(a.data, a.column, a.n_entities, composite_columns=composite_columns)
    print(f"dataset: {ds.source} entities={ds.n}")
    tasks = [(ds, s, n, o, a.n_records, a.ls, a.ks, a.q)
             for s in range(a.seeds) for n in a.noises for o in a.overlaps]
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
    pd.DataFrame(rows).to_csv(a.out, index=False)
    print(f"saved {len(rows)} rows -> {a.out}")


if __name__ == "__main__":
    main()
