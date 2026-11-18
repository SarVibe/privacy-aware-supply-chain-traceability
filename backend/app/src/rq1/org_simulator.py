"""
src/org_simulator.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Simulates heterogeneous real-world data entry practices across multi-tier supply chain stakeholders:
    1. Organization A (Manufacturer): Formal standard notation with catalog codes and brackets.
    2. Organization B (Distributor / Wholesaler): Uppercase ERP text, space-separated dosage, abbreviated units ('TAB', 'CAP').
    3. Organization C (Hospital / Pharmacy): Informal lowercase descriptions, trade name prioritization, slight typos.
- Retains ground truth 'true_entity_id' to rigorously evaluate cross-organizational harmonization pre-ledger.
"""

import os
import re
import random
import logging
from typing import List, Dict
import pandas as pd
from src.config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class CrossOrgSimulator:
    """
    Simulates multi-party supply chain data ingestion streams.
    """

    def __init__(
        self,
        clean_master_path: str = str(Config.MASTER_PRODUCTS_PATH),
        output_dir: str = str(Config.DATA_GENERATED_DIR),
        random_seed: int = Config.RANDOM_SEED
    ):
        self.clean_master_path = clean_master_path
        self.output_dir = output_dir
        self.random_seed = random_seed
        random.seed(self.random_seed)

        os.makedirs(self.output_dir, exist_ok=True)

    @staticmethod
    def _simulate_org_a(raw_desc: str) -> str:
        """
        Org A (Manufacturer):
        Maintains formal catalog style, preserving catalog code prefixes and brackets.
        Example: '#102198**Didanosine 200mg [Videx], tablets'
        """
        return raw_desc.strip()

    @staticmethod
    def _simulate_org_b(raw_desc: str) -> str:
        """
        Org B (Wholesaler / Distributor ERP):
        Uppercase system export, stripped punctuation, normalized abbreviations ('TAB', 'MG', 'ML').
        Example: 'DIDANOSINE 200 MG VIDEX TAB'
        """
        text = raw_desc.upper()
        # Remove inventory markers
        text = re.sub(r'#\d+\*+', '', text)
        # Standardize units and dosage abbreviations
        text = re.sub(r'\bTABLETS?\b', 'TAB', text)
        text = re.sub(r'\bCAPSULES?\b', 'CAP', text)
        # Separate numbers from dosage units: '200MG' -> '200 MG'
        text = re.sub(r'(\d+)\s*(MG|ML|G|MCG)\b', r'\1 \2', text)
        # Remove special punctuation
        text = re.sub(r'[^A-Z0-9\s]', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def _simulate_org_c(raw_desc: str) -> str:
        """
        Org C (Hospital / Retail Pharmacy):
        Informal lowercase input, trade names swapped to front, occasional minor typographical noise.
        Example: 'videx didanosine 200mg tabs'
        """
        text = raw_desc.lower()
        text = re.sub(r'#\d+\*+', '', text)

        # Extract bracketed trade name e.g. [Videx] and prioritize at the front
        bracket_match = re.search(r'\[(.*?)\]', text)
        trade_name = bracket_match.group(1).strip() if bracket_match else ""

        # Clean brackets and punctuation
        text = re.sub(r'\[.*?\]', '', text)
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        if trade_name:
            text = f"{trade_name} {text}"

        # 30% probability of minor typo (e.g. transposition or duplicate character)
        if random.random() < 0.30:
            words = text.split()
            if words:
                # Target the longest word to mutate
                target_idx = max(range(len(words)), key=lambda i: len(words[i]))
                target_word = list(words[target_idx])
                if len(target_word) > 4:
                    mutation = random.choice(["transpose", "duplicate", "delete"])
                    idx = random.randint(1, len(target_word) - 2)
                    if mutation == "transpose":
                        target_word[idx], target_word[idx + 1] = target_word[idx + 1], target_word[idx]
                    elif mutation == "duplicate":
                        target_word.insert(idx, target_word[idx])
                    elif mutation == "delete":
                        target_word.pop(idx)
                    words[target_idx] = "".join(target_word)
                    text = " ".join(words)

        return re.sub(r'\s+', ' ', text).strip()

    def generate_cross_org_dataset(self) -> pd.DataFrame:
        """
        Takes master product records and replicates them across Org A, Org B, and Org C.
        Saves the resulting dataset to 'data/generated/cross_org_simulation.csv'.
        """
        # Ensure deterministic re-runs
        random.seed(self.random_seed)

        if not os.path.exists(self.clean_master_path):
            raise FileNotFoundError(
                f"Master file not found at '{self.clean_master_path}'. "
                f"Please run 'src/data_loader.py' first."
            )

        df_master = pd.read_csv(self.clean_master_path)
        logger.info(f"Loaded {len(df_master)} master records to simulate multi-party supply chain ingestion.")

        simulated_records: List[Dict[str, str]] = []
        global_rec_idx = 1

        for _, row in df_master.iterrows():
            ent_id = str(row["true_entity_id"])
            raw_desc = str(row["raw_item_description"])

            # 1. Organization A: Manufacturer Submission
            simulated_records.append({
                "record_id": f"SIM_REC_{global_rec_idx:05d}",
                "true_entity_id": ent_id,
                "stakeholder_org": "Org_A_Manufacturer",
                "raw_item_description": self._simulate_org_a(raw_desc),
                "pack_size": str(row.get("pack_size", "Standard")),
                "vendor": str(row.get("vendor", "Manufacturer A"))
            })
            global_rec_idx += 1

            # 2. Organization B: Wholesaler/Distributor Submission
            simulated_records.append({
                "record_id": f"SIM_REC_{global_rec_idx:05d}",
                "true_entity_id": ent_id,
                "stakeholder_org": "Org_B_Wholesaler",
                "raw_item_description": self._simulate_org_b(raw_desc),
                "pack_size": str(row.get("pack_size", "Standard")),
                "vendor": str(row.get("vendor", "Generic Wholesaler"))
            })
            global_rec_idx += 1

            # 3. Organization C: Hospital/Pharmacy Submission
            simulated_records.append({
                "record_id": f"SIM_REC_{global_rec_idx:05d}",
                "true_entity_id": ent_id,
                "stakeholder_org": "Org_C_Hospital",
                "raw_item_description": self._simulate_org_c(raw_desc),
                "pack_size": str(row.get("pack_size", "Standard")),
                "vendor": str(row.get("vendor", "Local Pharmacy"))
            })
            global_rec_idx += 1

        df_sim = pd.DataFrame(simulated_records)
        output_path = os.path.join(self.output_dir, "cross_org_simulation.csv")
        df_sim.to_csv(output_path, index=False)
        logger.info(f"Successfully generated cross-organizational dataset: {len(df_sim)} records saved to '{output_path}'.")

        return df_sim


if __name__ == "__main__":
    simulator = CrossOrgSimulator()
    df_simulated = simulator.generate_cross_org_dataset()

    print("\n--- Cross-Organizational Simulation Sample ---")
    # Select a product entity with bracketed trade name to showcase the multi-tier transformation
    sample_candidates = df_simulated[
        (df_simulated["stakeholder_org"] == "Org_A_Manufacturer") & 
        (df_simulated["raw_item_description"].str.contains(r"\[.*\]", regex=True))
    ]
    sample_ent = sample_candidates["true_entity_id"].iloc[0] if len(sample_candidates) > 0 else df_simulated["true_entity_id"].iloc[0]
    sample_group = df_simulated[df_simulated["true_entity_id"] == sample_ent]
    print(f"Sample True Entity ID: {sample_ent}")
    for _, r in sample_group.iterrows():
        print(f"[{r['stakeholder_org']:20s}] -> '{r['raw_item_description']}'")