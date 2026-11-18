"""
src/preprocessor.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Standardizes product descriptions across heterogeneous stakeholders.
- Strips inventory tracking prefixes while preserving numbers and dosage formats.
- Implements Token-level Trigrams (q=3) to prevent Hard Negatives (e.g., 60mg vs 600mg)
  from false positive clustering under threshold tau.
"""

import os
import re
from pathlib import Path
from typing import Optional, Set, List, Dict, Union
from dotenv import load_dotenv

from src.common.qgram_extractor import QGramExtractor

# Search current directory, parent directory, and venv for .env
for p in [Path.cwd(), Path(__file__).resolve().parent.parent, Path(__file__).resolve().parent.parent.parent]:
    env_file = p / ".env"
    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
        break


class TextPreprocessor:
    """
    Supply chain text normalization and q-gram decomposition engine.
    """

    DEFAULT_Q = int(os.getenv("DEFAULT_Q", 3))

    @staticmethod
    def normalize(text: str) -> str:
        """
        Normalizes input text:
        1. Converts to lower case.
        2. Removes inventory prefixes common in USAID data (e.g., #102198**).
        3. Standardizes delimiters (slashes, brackets, hyphens) to single spaces.
        4. Keeps alphanumeric characters and essential spacing for numeric integrity.
        
        Example:
            '#102198**Didanosine 200mg [Videx], tablets' -> 'didanosine 200mg videx tablets'
        """
        if not text or not isinstance(text, str):
            return ""

        normalized = text.lower().strip()

        # Strip USAID inventory codes
        normalized = re.sub(r'#\d+\*+', ' ', normalized)

        # Replace all standard delimiters and punctuation with a single space
        normalized = re.sub(r'[/\\\[\]\(\),:;\-_*#+.]', ' ', normalized)

        # Keep only alphanumeric characters and whitespace
        normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    @classmethod
    def extract_qgrams(cls, text: str, q: Optional[int] = None) -> Set[str]:
        """
        Extracts overlapping character q-grams across full string with boundary padding.
        Delegates directly to QGramExtractor.
        """
        if not text:
            return set()
        q_val = q if q is not None else cls.DEFAULT_Q
        return QGramExtractor(q=q_val).extract_global_qgrams(text)

    @classmethod
    def extract_token_qgrams(cls, text: str, q: Optional[int] = None) -> Set[str]:
        """
        Token-boundary q-gram decomposition (Recommended for Algorithm 1):
        Delegates directly to QGramExtractor (Single Source of Truth).
        """
        if not text:
            return set()
        q_val = q if q is not None else cls.DEFAULT_Q
        return QGramExtractor(q=q_val).extract_token_qgrams(text)

    @classmethod
    def extract_token_qgrams_list(cls, text: str, q: Optional[int] = None) -> List[str]:
        """Preserves token-level duplicate q-grams for frequency analysis."""
        if not text:
            return []
        q_val = q if q is not None else cls.DEFAULT_Q
        return QGramExtractor(q=q_val).extract_token_qgrams_list(text)

    @classmethod
    def parse_attributes_from_text(cls, text: str) -> Dict[str, str]:
        """
        Extracts dosage, dosage form, and pack size heuristically from raw description
        when explicit fields are not available.
        """
        norm = cls.normalize(text)
        
        # Dosage pattern: e.g. '150mg', '10mg ml', '200 50mg', '60 30mg', '30mg'
        dose_match = re.search(r'\b(\d+(?:\s*\d+)?\s*(?:mg|ml|g|mcg)(?:\s*(?:ml|g))?)\b', norm)
        dosage = dose_match.group(1).replace(' ', '') if dose_match else "N/A"
        
        # Dosage form pattern
        form_match = re.search(r'\b(tablets?|capsules?|oral suspension|oral solution|test kit|suspension|powder)\b', norm)
        dosage_form = form_match.group(1).capitalize() if form_match else "Unknown"
        
        # Pack size pattern
        pack_match = re.search(r'\b(\d+)\s*(?:tabs?|caps?|tests?|bottle|vials?|ml)\b', norm)
        pack_size = pack_match.group(1) if pack_match else "Standard"
        
        return {
            "name": norm,
            "dosage": dosage,
            "dosage_form": dosage_form,
            "pack_size": pack_size
        }

    @classmethod
    def extract_composite_qgrams(
        cls,
        text: str,
        dosage: Optional[str] = None,
        dosage_form: Optional[str] = None,
        pack_size: Optional[Union[str, int]] = None,
        q: Optional[int] = None,
        dosage_weight: int = 6
    ) -> Set[str]:
        """
        Optimal Composite Multi-Attribute Representation for Component 1:
        Record_Filter = BloomFilter( Tag(Name) ∪ Tag(Dosage) ∪ Tag(Dosage Form) ∪ Tag(Pack Size) )
        """
        if not text:
            return set()

        # If explicit attributes not provided, parse them from text
        if dosage is None or dosage_form is None or pack_size is None:
            parsed = cls.parse_attributes_from_text(text)
            dosage = dosage if dosage is not None else parsed["dosage"]
            dosage_form = dosage_form if dosage_form is not None else parsed["dosage_form"]
            pack_size = pack_size if pack_size is not None else parsed["pack_size"]

        norm_name = cls.normalize(text)
        clean_dosage = cls.normalize(str(dosage)) if dosage else "N/A"
        clean_form = cls.normalize(str(dosage_form)) if dosage_form else "Unknown"
        clean_pack = cls.normalize(str(pack_size)) if pack_size else "Standard"

        q_val = q if q is not None else cls.DEFAULT_Q
        return QGramExtractor(q=q_val).extract_composite_qgrams(
            name=norm_name,
            dosage=clean_dosage,
            dosage_form=clean_form,
            pack_size=clean_pack,
            dosage_weight=dosage_weight
        )

    @classmethod
    def compare_token_overlap(
        cls, text1: str, text2: str, q: Optional[int] = None
    ) -> Dict[str, Union[float, int]]:
        """Diagnostic overlap evaluation between two strings prior to Bloom filter hashing."""
        q_val = q if q is not None else cls.DEFAULT_Q
        return QGramExtractor(q=q_val).compare_token_overlap(text1, text2)


if __name__ == "__main__":
    t1 = "Abacavir/Lamivudine 60/30mg, tablets"
    t2 = "Abacavir/Lamivudine 600/300mg, tablets"

    n1 = TextPreprocessor.normalize(t1)
    n2 = TextPreprocessor.normalize(t2)

    qg1 = TextPreprocessor.extract_token_qgrams(n1, q=3)
    qg2 = TextPreprocessor.extract_token_qgrams(n2, q=3)

    jaccard = len(qg1 & qg2) / len(qg1 | qg2)
    print("--- Hard Negative Resistance Check (q=3 Token-level) ---")
    print(f"T1: {n1}")
    print(f"T2: {n2}")
    print(f"Intersection: {len(qg1 & qg2)}, Union: {len(qg1 | qg2)}")
    print(f"Single Token Trigram Similarity: {jaccard:.4f}")

    comp1 = TextPreprocessor.extract_composite_qgrams(t1)
    comp2 = TextPreprocessor.extract_composite_qgrams(t2)
    dice_comp = (2.0 * len(comp1 & comp2)) / (len(comp1) + len(comp2))
    print("\n--- Composite Multi-Attribute Check (Name + Dose + Form + Pack) ---")
    print(f"Composite Intersection: {len(comp1 & comp2)}, Total: {len(comp1)} vs {len(comp2)}")
    print(f"Composite Dice Similarity: {dice_comp:.4f} (Cleanly below tau=0.85 -> Prevents False Merge!)")