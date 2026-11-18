"""Step 0/3: profile the dataset and predict Bloom-filter saturation for each (l, k).

Prints n_q (distinct q-grams per record) statistics and the expected fill ratio
1 - exp(-k * n_q / l); configurations above 0.95 are marked DEGENERATE.
"""
import argparse

import numpy as np
import pandas as pd

from src.config import Config
from src.rq2.config import DEFAULT_KS, DEFAULT_LS, DEFAULT_PAD, DEFAULT_Q, DEGENERATE_FILL
from src.rq2.data import load_dataset
from src.rq2.metrics import collision_load, expected_fill
from src.rq2.qgrams import qgram_set


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
    ap.add_argument("--q", type=int, default=DEFAULT_Q)
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
    nq = np.array([len(qgram_set(s, a.q, DEFAULT_PAD)) for s in ds.norm])
    print(f"dataset: {ds.source}  entities={ds.n}")
    print(f"n_q: mean={nq.mean():.1f}  p5={np.percentile(nq, 5):.0f}  p50={np.percentile(nq, 50):.0f}  "
          f"p95={np.percentile(nq, 95):.0f}  max={nq.max()}")
    rows = []
    for l in a.ls:
        for k in a.ks:
            load = collision_load(nq.mean(), k, l)
            rows.append({"l": l, "k": k, "load": round(load, 3), "expected_fill": round(expected_fill(load), 3),
                         "degenerate": int(expected_fill(load) > DEGENERATE_FILL)})
    df = pd.DataFrame(rows)
    print(df.pivot(index="l", columns="k", values="expected_fill").to_string())
    print(f"\nDEGENERATE (expected fill > {DEGENERATE_FILL}):")
    print(df[df.degenerate == 1][["l", "k", "expected_fill"]].to_string(index=False) or "none")
    df.to_csv(a.out, index=False)
    print(f"saved {a.out}")


if __name__ == "__main__":
    main()
