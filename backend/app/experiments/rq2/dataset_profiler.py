"""Step 0/3: profile the dataset and predict Bloom-filter saturation for each (l, k).

Prints n_q (distinct q-grams per record) statistics and the expected fill ratio
1 - exp(-k * n_q / l); configurations above 0.95 are marked DEGENERATE.
"""
import argparse

import numpy as np
import pandas as pd

from src.application_config import Config
from src.common.config import load_config
from src.common.encoding.qgrams import extract_qgrams
from src.common.experiment_metadata import add_common_args, write_run_csv
from src.rq2.experiment_config import DEFAULT_KS, DEFAULT_LS, DEFAULT_PAD, DEFAULT_Q
from src.rq2.rq2_dataset import load_dataset
from src.rq2.privacy_metrics import collision_load, expected_fill


def main():
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    ap.set_defaults(data=str(Config.RAW_DATA_PATH))
    ap.add_argument("--ls", type=int, nargs="+", default=list(DEFAULT_LS))
    ap.add_argument("--ks", type=int, nargs="+", default=list(DEFAULT_KS))
    ap.add_argument("--out", default=str(Config.RQ2_RAW_DIR / "profile_fill.csv"))
    a = ap.parse_args()

    composite_columns = (
        a.composite_columns
        if a.composite_columns is not None
        else ["dosage", "dosage_form", "pack_size"] if a.composite else None
    )
    ds = load_dataset(a.data, a.column, a.n_entities, composite_columns=composite_columns)
    pad_char = load_config("rq1").bloom.pad_char
    nq = np.array([len(extract_qgrams(s, a.q, pad_char)) if s else 0 for s in ds.norm])
    print(f"dataset: {ds.source}  entities={ds.n}")
    print(f"n_q: mean={nq.mean():.1f}  p5={np.percentile(nq, 5):.0f}  p50={np.percentile(nq, 50):.0f}  "
          f"p95={np.percentile(nq, 95):.0f}  max={nq.max()}")

    # ---- Entity-frequency distribution (T5 Part A) ----
    if getattr(ds, "counts", None) is not None:
        counts_arr = np.array([int(ds.counts[i]) for i in range(ds.n)], dtype=float)
    else:
        # Uniform weights — no actual count data
        counts_arr = np.ones(ds.n, dtype=float)
    counts_sorted = np.sort(counts_arr)[::-1]  # descending
    top10_share = counts_sorted[:10].sum() / max(1.0, counts_arr.sum())
    distinct_count_values = len(np.unique(counts_arr))
    print(f"\nEntity-frequency distribution:")
    print(f"  min={counts_sorted.min():.0f}  median={np.median(counts_arr):.0f}  "
          f"max={counts_sorted.max():.0f}  distinct_counts={distinct_count_values}")
    print(f"  top-10 share = {top10_share:.1%}")
    if top10_share > 0.5:
        print("  WARNING: top-10 entities account for >50% of counts "
              "(distribution is skewed → A2 frequency-alignment attack may be effective, "
              "but cross-seed variation will be high)")
    if distinct_count_values < 5:
        print("  WARNING: fewer than 5 distinct count values "
              "(basically uniform → A2 is uninformative / random-baseline level)")

    rows = []
    for l in a.ls:
        for k in a.ks:
            load = collision_load(nq.mean(), k, l)
            rows.append({"l": l, "k": k, "load": round(load, 3),
                         "expected_fill": round(expected_fill(load), 3)})
    df = pd.DataFrame(rows)
    print(df.pivot(index="l", columns="k", values="expected_fill").to_string())
    data_mode = "composite" if a.composite or a.composite_columns else "description"
    write_run_csv(df, a.out, q=a.q, pad=DEFAULT_PAD,
                  data_mode=data_mode, dataset_path=a.data)
    print(f"saved {a.out}")


if __name__ == "__main__":
    main()
