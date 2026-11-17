"""
experiments/noise_generator.py
Component 1: Experimental Evaluation Engine (RQ1 & RQ2)

Role:
- Reads canonical master product records from data/processed/clean_master_products.csv.
- Injects typographical errors into reproducible, seed-named datasets.
- Strictly preserves 'true_entity_id' to enable ground-truth evaluation of Precision, Recall, and F1.
- Generates reproducible datasets in data/synthetic_noisy/.
"""

import os
import random
import logging
from pathlib import Path
from typing import List, Optional
import pandas as pd
from dotenv import load_dotenv

# Search current directory, parent directory, and venv for .env
for p in [Path.cwd(), Path(__file__).resolve().parent.parent, Path(__file__).resolve().parent.parent.parent]:
    env_file = p / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
        break

from src.config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class SyntheticNoiseGenerator:
    """
    Simulates typographical inconsistencies in multi-organization supply chain data:
    1. Substitution: 'paracetamol' -> 'parasetamol'
    2. Deletion:     'amoxicillin' -> 'amoxicilin'
    3. Insertion:    'aspirin'     -> 'asspirin'
    4. Transposition:'ibuprofen'   -> 'ibuproefn'
    """

    def __init__(
        self,
        clean_master_path: Optional[str] = None,
        output_dir: Optional[str] = None,
        random_seed: Optional[int] = None
    ):
        self.clean_master_path = str(clean_master_path or Config.MASTER_PRODUCTS_PATH)
        self.output_dir = str(output_dir or Config.DATA_SYNTHETIC_DIR)
        self.random_seed = int(random_seed if random_seed is not None else Config.RANDOM_SEED)
        self.alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"

        os.makedirs(self.output_dir, exist_ok=True)

    def _inject_typo(self, text: str, noise_rate: float, rng: random.Random) -> str:
        """
        Mutates characters within text proportional to noise_rate.
        Leaves short numbers (< 3 digits) intact when possible to prevent random number corruptions.
        """
        if noise_rate <= 0.0 or not text:
            return text

        chars = list(text)
        num_mutations = max(1, int(len(chars) * noise_rate))

        for _ in range(num_mutations):
            if len(chars) <= 3:
                break

            mutation = rng.choice(["substitute", "delete", "insert", "transpose"])
            idx = rng.randint(0, len(chars) - 1)

            if mutation == "substitute":
                chars[idx] = rng.choice(self.alphabet)

            elif mutation == "delete" and len(chars) > 3:
                chars.pop(idx)

            elif mutation == "insert":
                chars.insert(idx, rng.choice(self.alphabet))

            elif mutation == "transpose" and idx < len(chars) - 1:
                chars[idx], chars[idx + 1] = chars[idx + 1], chars[idx]

        return "".join(chars)

    def generate_noisy_datasets(
        self,
        noise_levels: Optional[List[int]] = None,
        seeds: Optional[List[int]] = None,
        all_fields: bool = False,
    ) -> None:
        """
        Generates noisy dataset variations while preserving 'true_entity_id'.
        """
        if noise_levels is None:
            raw_levels = os.getenv("DEFAULT_NOISE_LEVELS", "0,5,15,30")
            noise_levels = [int(x.strip()) for x in raw_levels.split(",") if x.strip()]

        if not os.path.exists(self.clean_master_path):
            raise FileNotFoundError(
                f"Master file not found at '{self.clean_master_path}'. "
                f"Please run 'src/data_loader.py' first."
            )

        df_master = pd.read_csv(self.clean_master_path)
        logger.info(f"Loaded {len(df_master)} master records from {self.clean_master_path}")

        if seeds is None:
            seeds = [self.random_seed]

        for seed in seeds:
            rng = random.Random(seed)
            for noise_pct in noise_levels:
                noise_rate = noise_pct / 100.0
                noisy_rows = []

                for _, row in df_master.iterrows():
                    noisy = {
                        "raw_item_description": str(row["raw_item_description"]),
                        "dosage": row.get("dosage", "N/A"),
                        "dosage_form": row.get("dosage_form", "Unknown"),
                        "pack_size": row.get("pack_size", "Standard"),
                    }
                    fields = list(noisy) if all_fields else ["raw_item_description"]
                    if noise_pct:
                        for field in fields:
                            noisy[field] = self._inject_typo(str(noisy[field]), noise_rate, rng)

                    noisy_rows.append({
                        "record_id": row["record_id"],
                        "true_entity_id": row["true_entity_id"],
                        **noisy,
                        "vendor": row.get("vendor", "Generic"),
                        "noise_level_pct": noise_pct
                    })

                df_noisy = pd.DataFrame(noisy_rows)
                out_path = os.path.join(self.output_dir, f"noisy_products_{noise_pct}_seed{seed}.csv")
                df_noisy.to_csv(out_path, index=False)
                logger.info(f"Generated {out_path} ({len(df_noisy)} records, {noise_pct}% noise)")

        logger.info("All synthetic noisy datasets successfully generated.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate seeded RQ1 noisy datasets")
    parser.add_argument("--seeds", nargs="+", type=int, default=[42], help="dataset seeds")
    parser.add_argument("--noise-levels", nargs="+", type=int, default=None)
    parser.add_argument("--all-fields", action="store_true", help="mutate structured fields as well")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    output_dir = args.output_dir
    if output_dir is None and args.all_fields:
        output_dir = str(Config.DATA_SYNTHETIC_ALL_FIELDS_DIR)
    SyntheticNoiseGenerator(output_dir=output_dir).generate_noisy_datasets(
        noise_levels=args.noise_levels, seeds=args.seeds, all_fields=args.all_fields
    )