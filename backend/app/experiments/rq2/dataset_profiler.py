"""Step 0/3: profile the dataset and predict Bloom-filter saturation for each (l, k).

Prints n_q (distinct q-grams per record) statistics and the expected fill ratio
1 - exp(-k * n_q / l); configurations above 0.95 are marked DEGENERATE.
"""
import argparse

import numpy as np
import pandas as pd

from src.application_config import Config
from src.common.experiment_metadata import add_common_args, write_run_csv
from src.rq2.experiment_config import DEFAULT_KS, DEFAULT_LS, DEFAULT_PAD, DEFAULT_Q
from src.rq2.rq2_dataset import load_dataset
from src.rq2.privacy_metrics import collision_load, expected_fill
from src.rq2.qgram_utils import qgram_set


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
    nq = np.array([len(qgram_set(s, a.q, DEFAULT_PAD)) for s in ds.norm])
    print(f"dataset: {ds.source}  entities={ds.n}")
    print(f"n_q: mean={nq.mean():.1f}  p5={np.percentile(nq, 5):.0f}  p50={np.percentile(nq, 50):.0f}  "
          f"p95={np.percentile(nq, 95):.0f}  max={nq.max()}")
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
