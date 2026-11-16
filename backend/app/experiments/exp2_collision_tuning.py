"""
RQ2: Bloom-filter length and hash-count collision tuning.
"""

import os
from typing import Optional, Sequence

import pandas as pd

from src.config import Config
from src.data_loader import SupplyChainDataLoader
from src.keyed_bloom_filter import KeyedBloomFilter
from src.preprocessor import TextPreprocessor


def _load_master() -> pd.DataFrame:
    if not Config.MASTER_PRODUCTS_PATH.exists():
        return SupplyChainDataLoader().run()[0]
    return pd.read_csv(Config.MASTER_PRODUCTS_PATH)


def run_collision_tuning(
    df_master: Optional[pd.DataFrame] = None,
    lengths: Optional[Sequence[int]] = None,
    hash_counts: Optional[Sequence[int]] = None,
) -> pd.DataFrame:
    df = df_master if df_master is not None else _load_master()
    lengths = list(lengths or Config.RQ2_LENGTH_GRID)
    hash_counts = list(hash_counts or Config.RQ2_HASH_GRID)
    rows = []

    qgram_sets = [
        TextPreprocessor.extract_composite_qgrams(
            text=str(row["raw_item_description"]),
            dosage=row.get("dosage"),
            dosage_form=row.get("dosage_form"),
            pack_size=row.get("pack_size"),
            q=Config.DEFAULT_Q,
        )
        for _, row in df.iterrows()
    ]

    for length in lengths:
        for num_hashes in hash_counts:
            engine = KeyedBloomFilter(
                length=length,
                num_hashes=num_hashes,
                secret_key=Config.SHARED_SECRET_KEY,
            )
            filters = [engine.encode(qgrams) for qgrams in qgram_sets]
            serialized = {KeyedBloomFilter.to_bytes(value) for value in filters}
            density = [
                KeyedBloomFilter.calculate_bit_density(value) for value in filters
            ]
            total = len(filters)
            rows.append(
                {
                    "filter_length": length,
                    "num_hashes": num_hashes,
                    "records": total,
                    "unique_filters": len(serialized),
                    "collision_count": total - len(serialized),
                    "collision_rate": (total - len(serialized)) / total
                    if total
                    else 0.0,
                    "average_bit_density": sum(density) / total if total else 0.0,
                }
            )

    result = pd.DataFrame(rows)
    output_path = Config.TABLES_DIR / "rq2_collision_tuning.csv"
    result.to_csv(output_path, index=False)
    return result


if __name__ == "__main__":
    configured_lengths = os.getenv("RQ2_LENGTHS")
    configured_hashes = os.getenv("RQ2_HASH_COUNTS")
    result = run_collision_tuning(
        lengths=[int(value) for value in configured_lengths.split(",")]
        if configured_lengths
        else None,
        hash_counts=[int(value) for value in configured_hashes.split(",")]
        if configured_hashes
        else None,
    )
    print(result.to_string(index=False))