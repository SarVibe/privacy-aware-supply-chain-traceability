"""
src/application_config.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Central configuration manager loading environment variables from .env.
- Provides defaults for Algorithm 1 (l=1024, k=4, tau=0.85, q=3).
- Provides parameter grids for Supervisor's Research Questions:
    - RQ1: Noise levels [0, 5, 15, 30]
    - RQ2: Filter lengths l in [256, 512, 1024], Hash counts k in [4, 8, 16, 30]
    - RQ3: Privacy budgets epsilon in [0.2, 0.5, 1.0, 2.0, 5.0]
- Establishes global paths for datasets, logs, and experiment results.
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Tuple
from dotenv import load_dotenv

# Application data directory
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent.parent

# Load the single project-level environment file used by every component.
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_FILE)


@dataclass(frozen=True)
class ExperimentConfig:
    q: int = 2
    pad: bool = False
    tau_grid: Tuple[float, ...] = tuple(
        float(round(v, 4)) for v in __import__("numpy").arange(0.30, 1.0001, 0.005)
    )
    degenerate_fill: float = 0.95
    standard: Tuple[int, int] = (1024, 4)
    reid_topk: Tuple[int, ...] = (1, 5, 10)
    reid_delta: float = 0.02
    bit_top: int = 100
    n_entities: int = 1000
    n_records: int = 3000
    seeds: Tuple[int, ...] = tuple(range(20))
    extra_columns: Tuple[str, ...] = ("dosage", "dosage_form", "pack_size")
    tau_primary: float = 0.85
    tau_secondary: float = 0.80
    bloom_length: int = 1024
    k_primary: int = 4
    k_secondary: int = 30
    rq1_noise_min_len: int = 3
    rq1_noise_min_edits: int = 1


EXPERIMENT_CONFIG = ExperimentConfig()


class Config:
    """Global configuration registry for Component 1."""

    BASE_DIR = BASE_DIR
    PROJECT_ROOT = PROJECT_ROOT
    ENV_FILE = ENV_FILE

    # ==========================================
    # 1. Cryptographic Secrets
    # ==========================================
    SHARED_SECRET_KEY: bytes = os.getenv(
        "SHARED_SECRET_KEY", 
        "c1_pharma_consortium_super_secret_salt_2026_xyz"
    ).encode("utf-8")

    BLOCKCHAIN_PRIVATE_KEY: str = os.getenv("BLOCKCHAIN_PRIVATE_KEY", "")

    # ==========================================
    # 2. Blockchain / Web3 Settings
    # ==========================================
    BLOCKCHAIN_RPC_URL: str = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
    CONTRACT_ADDRESS: str = os.getenv("CONTRACT_ADDRESS", "0x5FbDB2315678afecb367f032d93F642f64180aa3")
    CHAIN_ID: int = int(os.getenv("CHAIN_ID", "31337"))  # Default: Hardhat Network ID
    ALLOW_MOCK_LEDGER: bool = os.getenv("ALLOW_MOCK_LEDGER", "false").strip().lower() == "true"
    API_ENABLE_BLOCKCHAIN_COMMIT: bool = (
        os.getenv("API_ENABLE_BLOCKCHAIN_COMMIT", "false").strip().lower() == "true"
    )

    # ==========================================
    # 3. Algorithm 1 Default Hyperparameters
    # ==========================================
    DEFAULT_BF_LENGTH: int = int(os.getenv("DEFAULT_BF_LENGTH", "1024"))      # Bit length (l)
    DEFAULT_NUM_HASHES: int = int(os.getenv("DEFAULT_NUM_HASHES", "4"))       # Hash count (k)
    DEFAULT_SIMILARITY_THRESHOLD: float = float(os.getenv("DEFAULT_SIMILARITY_THRESHOLD", "0.92"))  # tau
    DEFAULT_Q: int = int(os.getenv("DEFAULT_Q", "3"))                         # Token Trigrams (q=3)
    DEFAULT_EPSILON: float = float(os.getenv("DEFAULT_EPSILON", "1.0"))       # Balanced DP budget

    RANDOM_SEED: int = int(os.getenv("RANDOM_SEED", "42"))

    # ==========================================
    # 4. Storage & Directory Paths
    # ==========================================
    RAW_DATA_PATH = BASE_DIR / os.getenv("RAW_DATA_PATH", "data/raw/Suppy_Chain_Shipment_Data.csv")
    DATA_RAW_DIR = RAW_DATA_PATH.parent
    DATA_GENERATED_DIR = BASE_DIR / os.getenv("GENERATED_DATA_DIR", "data/generated")
    DATA_SYNTHETIC_ALL_FIELDS_DIR = DATA_GENERATED_DIR

    MASTER_PRODUCTS_PATH = DATA_GENERATED_DIR / "clean_master_products.csv"
    ENTITY_CATALOG_PATH = DATA_GENERATED_DIR / "entity_catalog.csv"
    GROUND_TRUTH_PAIRS_PATH = DATA_GENERATED_DIR / "ground_truth_pairs.csv"

    RESULTS_DIR = BASE_DIR / "results"
    RQ1_RESULTS_DIR = RESULTS_DIR / "rq1"
    RQ1_RAW_DIR = RQ1_RESULTS_DIR / "raw"
    RQ1_TABLES_DIR = RQ1_RESULTS_DIR / "tables"
    RQ1_FIGURES_DIR = RQ1_RESULTS_DIR / "figures"
    RQ2_RESULTS_DIR = RESULTS_DIR / "rq2"
    RQ2_RAW_DIR = RQ2_RESULTS_DIR / "raw"
    RQ2_TABLES_DIR = RQ2_RESULTS_DIR / "tables"
    RQ2_FIGURES_DIR = RQ2_RESULTS_DIR / "figures"
    # Backwards-compatible default result aliases.
    FIGURES_DIR = RQ1_FIGURES_DIR
    TABLES_DIR = RQ1_TABLES_DIR

    # ==========================================
    # 5. Experimental Parameter Grids
    # ==========================================
    # RQ1: Robustness against data errors
    RQ1_NOISE_LEVELS = [0, 5, 15, 30]

    # RQ2: Collision Tuning & Probable Privacy
    RQ2_LENGTH_GRID = [256, 512, 1024]
    RQ2_HASH_GRID = [4, 8, 16, 30]

    # RQ3: Local Differential Privacy & Provable Privacy
    RQ3_EPSILON_GRID = [0.2, 0.5, 1.0, 2.0, 5.0]

    @classmethod
    def ensure_directories(cls):
        """Ensures that all runtime and export folders exist."""
        for path in [
            cls.DATA_RAW_DIR,
            cls.DATA_GENERATED_DIR,
            cls.DATA_SYNTHETIC_ALL_FIELDS_DIR,
            cls.RQ1_RAW_DIR,
            cls.RQ1_TABLES_DIR,
            cls.RQ1_FIGURES_DIR,
            cls.RQ2_RAW_DIR,
            cls.RQ2_TABLES_DIR,
            cls.RQ2_FIGURES_DIR,
        ]:
            path.mkdir(parents=True, exist_ok=True)


# Auto-create folders on module import
Config.ensure_directories()


if __name__ == "__main__":
    print("--- Component 1 Configuration Loaded ---")
    print(f"Base Directory:     {BASE_DIR}")
    print(f"Master Products:    {Config.MASTER_PRODUCTS_PATH}")
    print(f"Default Parameters: l={Config.DEFAULT_BF_LENGTH}, k={Config.DEFAULT_NUM_HASHES}, tau={Config.DEFAULT_SIMILARITY_THRESHOLD}, q={Config.DEFAULT_Q}")
    print(f"Default DP Epsilon: {Config.DEFAULT_EPSILON}")
    print(f"Blockchain RPC:     {Config.BLOCKCHAIN_RPC_URL}")