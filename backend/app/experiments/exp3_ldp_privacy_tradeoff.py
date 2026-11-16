"""
RQ3: Local differential-privacy utility trade-off.
"""

from typing import Optional, Sequence

import pandas as pd

from src.config import Config
from src.data_loader import SupplyChainDataLoader
from src.differential_privacy import LocalDifferentialPrivacy
from src.keyed_bloom_filter import KeyedBloomFilter
from src.preprocessor import TextPreprocessor
from src.similarity import DiceSimilarityEngine


def _load_master() -> pd.DataFrame:
    if not Config.MASTER_PRODUCTS_PATH.exists():
        return SupplyChainDataLoader().run()[0]
    return pd.read_csv(Config.MASTER_PRODUCTS_PATH)


def run_ldp_tradeoff(
    df_master: Optional[pd.DataFrame] = None,
    epsilons: Optional[Sequence[float]] = None,
) -> pd.DataFrame:
    df = df_master if df_master is not None else _load_master()
    epsilons = list(epsilons or Config.RQ3_EPSILON_GRID)
    engine = KeyedBloomFilter(
        length=Config.DEFAULT_BF_LENGTH,
        num_hashes=Config.DEFAULT_NUM_HASHES,
        secret_key=Config.SHARED_SECRET_KEY,
    )
    clean_filters = [
        engine.encode(
            TextPreprocessor.extract_composite_qgrams(
                text=str(row["raw_item_description"]),
                dosage=row.get("dosage"),
                dosage_form=row.get("dosage_form"),
                pack_size=row.get("pack_size"),
                q=Config.DEFAULT_Q,
            )
        )
        for _, row in df.iterrows()
    ]
    rows = []

    for epsilon in epsilons:
        noisy_filters = [
            LocalDifferentialPrivacy.apply_randomized_response(
                value,
                epsilon=epsilon,
                seed=Config.RANDOM_SEED + index,
            )
            for index, value in enumerate(clean_filters)
        ]
        if clean_filters:
            densities = [
                KeyedBloomFilter.calculate_bit_density(value)
                for value in noisy_filters
            ]
            flip_rates = [
                (clean ^ noisy).count(1) / len(clean)
                for clean, noisy in zip(clean_filters, noisy_filters)
            ]
            similarities = [
                DiceSimilarityEngine.calculate_dice(clean, noisy)
                for clean, noisy in zip(clean_filters, noisy_filters)
            ]
            rows.append(
                {
                    "epsilon": epsilon,
                    "records": len(noisy_filters),
                    "theoretical_flip_probability": LocalDifferentialPrivacy.calculate_flip_probability(
                        epsilon
                    ),
                    "average_flip_rate": sum(flip_rates) / len(flip_rates),
                    "average_bit_density": sum(densities) / len(densities),
                    "average_clean_noisy_dice": sum(similarities) / len(similarities),
                }
            )

    result = pd.DataFrame(rows)
    output_path = Config.TABLES_DIR / "rq3_ldp_privacy_tradeoff.csv"
    result.to_csv(output_path, index=False)
    return result


if __name__ == "__main__":
    print(run_ldp_tradeoff().to_string(index=False))