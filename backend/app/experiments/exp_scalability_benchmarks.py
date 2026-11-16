"""
Scalability benchmark for the off-chain harmonization pipeline.
"""

import os
import time
from typing import Optional, Sequence

import pandas as pd

from src.config import Config
from src.data_loader import SupplyChainDataLoader
from src.harmonization_pipeline import HarmonizationPipeline


def _load_master() -> pd.DataFrame:
    if not Config.MASTER_PRODUCTS_PATH.exists():
        return SupplyChainDataLoader().run()[0]
    return pd.read_csv(Config.MASTER_PRODUCTS_PATH)


def run_scalability_benchmark(
    df_master: Optional[pd.DataFrame] = None,
    sizes: Optional[Sequence[int]] = None,
) -> pd.DataFrame:
    df = df_master if df_master is not None else _load_master()
    if sizes is None:
        configured_sizes = os.getenv("SCALABILITY_SIZES")
        sizes = (
            [int(value) for value in configured_sizes.split(",")]
            if configured_sizes
            else [10, 50, 100, 500, 1000]
        )

    rows = []
    for requested_size in sizes:
        size = min(int(requested_size), len(df))
        if size <= 0:
            continue
        pipeline = HarmonizationPipeline(enable_blockchain_commit=False)
        batch = df.head(size).copy()
        started = time.perf_counter()
        result = pipeline.process_batch(batch)
        elapsed_seconds = time.perf_counter() - started
        rows.append(
            {
                "requested_records": int(requested_size),
                "processed_records": size,
                "elapsed_seconds": round(elapsed_seconds, 6),
                "records_per_second": round(size / elapsed_seconds, 3)
                if elapsed_seconds
                else 0.0,
                "average_total_latency_ms": round(
                    float(result["total_latency_ms"].mean()), 4
                ),
                "clusters": int(result["predicted_cluster_id"].nunique()),
            }
        )

    result = pd.DataFrame(rows)
    output_path = Config.TABLES_DIR / "scalability_benchmark.csv"
    result.to_csv(output_path, index=False)
    return result


if __name__ == "__main__":
    print(run_scalability_benchmark().to_string(index=False))