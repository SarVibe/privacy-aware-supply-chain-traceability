"""Deprecated legacy dataset profiler. The collision runner profiles its own cohorts."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.config import load_config
from src.common.data.loader import BASE_DATASET_FILENAME
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.experiment.runner import iter_grid
from src.common.experiment_metadata import write_run_csv
from src.common.paths import prepared_dir, results_dir
from src.rq2.privacy_metrics import collision_load, expected_fill
from src.rq2.rq2_dataset import load_research_dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["reduced", "extended"], default="reduced")
    parser.add_argument("--ls", type=int, nargs="+")
    parser.add_argument("--ks", type=int, nargs="+")
    parser.add_argument("--max-records", type=int, help="limit prepared records by whole entity groups")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    cfg = load_config("rq2" if args.profile == "reduced" else "rq2_extended")
    sweep = cfg.sweep
    ds = load_research_dataset(cfg, cfg.seeds[0], 0, max_records=args.max_records)
    bloom = cfg.bloom
    encoder = BloomFilterEncoder(bloom.l, bloom.k, bloom.q, bytes.fromhex(bloom.hmac_key), bloom.pad_char)
    grams = np.array([len(encoder.grams(text)) for text in ds.norm])
    mean = float(grams.mean())
    counts = np.sort(ds.counts)[::-1]
    print(f"{ds.n} entities, {mean:.1f} distinct q-grams per entity on average")
    print(f"Entity counts range from {counts.min()} to {counts.max()}. "
          f"Top 10 share: {counts[:10].sum() / counts.sum():.1%}")

    rows = []
    for point in iter_grid({"l": args.ls or sweep.lengths, "k": args.ks or sweep.hashes}):
        load = collision_load(mean, point["k"], point["l"])
        rows.append({**point, "load": load, "expected_fill": expected_fill(load)})
    table = pd.DataFrame(rows)
    print(table.pivot(index="l", columns="k", values="expected_fill").to_string(float_format="{:.3f}".format))
    out = args.out or results_dir(cfg, "rq2") / sweep.profile_csv
    write_run_csv(table, out, cfg=cfg, data_mode="composite",
                  dataset_path=str(prepared_dir(cfg) / BASE_DATASET_FILENAME))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
