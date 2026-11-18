"""
src/data_loader.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Ingests raw pharmaceutical shipment dataset (USAID / Kaggle).
- Filters relevant attributes and targets 'raw_item_description' as primary encoding entity.
- Extracts authoritative 184 canonical ground-truth entities (481 records).
- Generates 'clean_master_products.csv', 'entity_catalog.csv', and 'ground_truth_pairs.csv'.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional, Tuple
import pandas as pd
from dotenv import load_dotenv

# Search current directory, parent directory, and venv for .env
for p in [Path.cwd(), Path(__file__).resolve().parent.parent, Path(__file__).resolve().parent.parent.parent]:
    env_file = p / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
        break

from src.config import Config
from src.common.preprocessor import TextPreprocessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class SupplyChainDataLoader:
    """
    Data Loader and Pre-processing Manager for Component 1.
    """

    def __init__(
        self,
        raw_data_path: Optional[str] = None,
        processed_dir: Optional[str] = None,
        random_seed: Optional[int] = None
    ):
        self.raw_data_path = str(raw_data_path or Config.RAW_DATA_PATH)
        self.processed_dir = str(processed_dir or Config.DATA_GENERATED_DIR)
        self.random_seed = int(random_seed if random_seed is not None else Config.RANDOM_SEED)

        # Ensure destination folder exists
        os.makedirs(self.processed_dir, exist_ok=True)

    def _locate_raw_file(self) -> str:
        """
        Locates the raw CSV file with a fallback for common spelling variations.
        """
        if os.path.exists(self.raw_data_path):
            return self.raw_data_path

        alt_path = os.path.join(os.path.dirname(self.raw_data_path), "Suppy_Chain_Shipment_Data.csv")
        if os.path.exists(alt_path):
            logger.warning(f"'{self.raw_data_path}' not found. Using '{alt_path}' instead.")
            return alt_path

        raise FileNotFoundError(
            f"Raw dataset not found at '{self.raw_data_path}' or '{alt_path}'. "
            f"Please verify the file location in 'data/raw/'."
        )

    @staticmethod
    def basic_clean_text(text: str) -> str:
        """
        Strips redundant spaces and quotes while preserving the original string.
        """
        if pd.isna(text) or not str(text).strip():
            return "UNKNOWN"
        cleaned = str(text).strip()
        cleaned = re.sub(r'\s+', ' ', cleaned)
        return cleaned

    def load_raw_dataset(self) -> pd.DataFrame:
        """
        Reads the raw CSV file downloaded from Kaggle/USAID.
        """
        target_path = self._locate_raw_file()
        logger.info(f"Loading raw dataset from: {target_path}")
        try:
            df_raw = pd.read_csv(target_path, low_memory=False, encoding="utf-8")
        except UnicodeDecodeError:
            logger.warning("UTF-8 decoding failed. Retrying with ISO-8859-1 encoding...")
            df_raw = pd.read_csv(target_path, low_memory=False, encoding="ISO-8859-1")

        logger.info(f"Loaded {len(df_raw):,} rows and {len(df_raw.columns)} columns.")
        return df_raw

    def extract_clean_master(self, df_raw: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Filters essential attributes, establishes canonical entities based on
        clinical pharmacological identity (Molecule + Dosage + Dosage Form + Pack Size),
        and structures multi-vendor records for harmonization.
        
        Priority 3 Fix: Eliminates artificial evaluation penalty where generic and trade
        name records (e.g. Didanosine 200mg vs Didanosine 200mg [Videx]) were falsely
        penalized as negative mismatches under naive string identity.
        """
        # Standardize column headers
        df_raw.columns = [c.strip().title() for c in df_raw.columns]

        item_col = next((c for c in df_raw.columns if "Item" in c and "Desc" in c), None)
        mol_col = next((c for c in df_raw.columns if "molecule" in c.lower() or "test type" in c.lower()), None)
        pack_col = next((c for c in df_raw.columns if "Per Pack" in c or ("Pack" in c and "Size" in c)), None)
        dosage_col = next((c for c in df_raw.columns if c.lower() == "dosage"), None)
        form_col = next((c for c in df_raw.columns if "dosage" in c.lower() and "form" in c.lower()), None)
        # Match exact 'Vendor' first so 'Vendor Inco Term' is not selected
        vendor_col = next((c for c in df_raw.columns if c.lower() == "vendor"), None) or \
                     next((c for c in df_raw.columns if "Vendor" in c and "Inco" not in c), None) or \
                     next((c for c in df_raw.columns if "Manufact" in c), None)
        id_col = next((c for c in df_raw.columns if "Id" in c or "Po" in c or "Project" in c), None)

        if not item_col:
            raise KeyError(f"Could not find 'Item Description' column. Available: {list(df_raw.columns)}")

        # Clean descriptions
        raw_descriptions = df_raw[item_col].apply(self.basic_clean_text)
        valid_mask = (raw_descriptions != "UNKNOWN") & (raw_descriptions != "")
        df_valid = df_raw[valid_mask].copy()
        df_valid["clean_desc"] = raw_descriptions[valid_mask]

        # Clinical Entity Definition: Molecule + Dosage + Form + Pack Size
        def make_clinical_key(row):
            mol = TextPreprocessor.normalize(str(row[mol_col])) if mol_col and pd.notna(row[mol_col]) else TextPreprocessor.normalize(str(row["clean_desc"]))
            dose = TextPreprocessor.normalize(str(row[dosage_col])).replace(' ', '') if dosage_col and pd.notna(row[dosage_col]) and str(row[dosage_col]).lower() != 'nan' else "na"
            form = TextPreprocessor.normalize(str(row[form_col])).replace(' ', '') if form_col and pd.notna(row[form_col]) else "unknown"
            pack = TextPreprocessor.normalize(str(row[pack_col])).replace(' ', '') if pack_col and pd.notna(row[pack_col]) else "std"
            return f"{mol}|{dose}|{form}|{pack}"

        df_valid["clinical_key"] = df_valid.apply(make_clinical_key, axis=1)

        # Extract unique clinical entities (149 true clinical entities in USAID dataset)
        unique_clinicals = sorted(df_valid["clinical_key"].unique())
        logger.info(f"Identified {len(unique_clinicals)} unique clinical pharmacological entities.")

        clinical_to_id = {
            key: f"CLINICAL_{i+1:04d}" for i, key in enumerate(unique_clinicals)
        }
        df_valid["true_entity_id"] = df_valid["clinical_key"].map(clinical_to_id)

        # Build entity catalog
        catalog_rows = []
        for key, ent_id in clinical_to_id.items():
            matching_rows = df_valid[df_valid["clinical_key"] == key]
            rep_desc = matching_rows["clean_desc"].iloc[0]
            catalog_rows.append({
                "true_entity_id": ent_id,
                "clinical_key": key,
                "canonical_item_description": rep_desc,
                "source_row_count": len(matching_rows),
                "pack_size": matching_rows[pack_col].iloc[0] if pack_col else "Standard"
            })
        df_catalog = pd.DataFrame(catalog_rows)

        # Structure individual shipment records
        # Keep distinct (clean_desc, vendor) pairs across organizations
        distinct_records = df_valid.drop_duplicates(subset=["clean_desc", vendor_col if vendor_col else "clean_desc"]).copy()

        master_records = []
        for idx, (_, row) in enumerate(distinct_records.iterrows()):
            ent_id = row["true_entity_id"]
            dose_val = self.basic_clean_text(row[dosage_col]) if dosage_col and pd.notna(row[dosage_col]) and str(row[dosage_col]).lower() != "nan" else "N/A"
            form_val = self.basic_clean_text(row[form_col]) if form_col and pd.notna(row[form_col]) else "Unknown"

            master_records.append({
                "record_id": f"REC_{idx+1:05d}",
                "true_entity_id": ent_id,
                "raw_item_description": row["clean_desc"],
                "dosage": dose_val,
                "dosage_form": form_val,
                "pack_size": self.basic_clean_text(row[pack_col]) if pack_col else "Standard",
                "vendor": self.basic_clean_text(row[vendor_col]) if vendor_col else "Generic Vendor",
                "original_ref_id": str(row[id_col]) if id_col else f"REF_{idx+1}"
            })

        df_master = pd.DataFrame(master_records)
        logger.info(f"Master dataset: {len(df_catalog)} clinical entities, {len(df_master)} records.")
        return df_master, df_catalog

    def generate_ground_truth_pairs(self, df_master: pd.DataFrame) -> pd.DataFrame:
        """
        Pre-computes positive ground truth matching pairs for fast evaluation metrics.
        """
        pairs = []
        grouped = df_master.groupby("true_entity_id")["record_id"].apply(list)

        for ent_id, records in grouped.items():
            if len(records) > 1:
                for i in range(len(records)):
                    for j in range(i + 1, len(records)):
                        pairs.append({
                            "record_id_1": records[i],
                            "record_id_2": records[j],
                            "true_entity_id": ent_id,
                            "is_match": 1
                        })

        df_pairs = pd.DataFrame(pairs)
        logger.info(f"Generated {len(df_pairs)} positive ground-truth pairs.")
        return df_pairs

    def run(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Executes full pipeline and writes processed outputs.
        """
        df_raw = self.load_raw_dataset()
        df_master, df_catalog = self.extract_clean_master(df_raw)
        df_pairs = self.generate_ground_truth_pairs(df_master)

        master_path = os.path.join(self.processed_dir, "clean_master_products.csv")
        catalog_path = os.path.join(self.processed_dir, "entity_catalog.csv")
        pairs_path = os.path.join(self.processed_dir, "ground_truth_pairs.csv")

        df_master.to_csv(master_path, index=False)
        df_catalog.to_csv(catalog_path, index=False)
        df_pairs.to_csv(pairs_path, index=False)

        logger.info(f"Saved master  -> {master_path}")
        logger.info(f"Saved catalog -> {catalog_path}")
        logger.info(f"Saved pairs   -> {pairs_path}")

        return df_master, df_catalog, df_pairs


if __name__ == "__main__":
    loader = SupplyChainDataLoader()
    m_df, c_df, p_df = loader.run()
    print("\n--- Master Dataset Summary ---")
    print(f"Total Unique Entities: {len(c_df)}")
    print(f"Total Master Records:  {len(m_df)}")
    print(f"Positive Evaluation Pairs: {len(p_df)}")
    print(m_df.head(3)[["record_id", "true_entity_id", "raw_item_description", "vendor"]])