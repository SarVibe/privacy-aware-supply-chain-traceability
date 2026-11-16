"""
src/qgram_extractor.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Token-level q-gram extraction engine for pharmaceutical descriptions.
- Implements boundary padding ('_' padding) to capture prefix and suffix semantics.
- Generates token-level trigrams (default q=3) to prevent False Positive merges on
  critical dosage differences (e.g., '60mg' vs '600mg' - Hard Negatives).
- Supports both unique Set-based q-grams and positional/frequency q-grams.
"""

import re
from typing import Set, List, Dict, Union, Optional
from src.config import Config


class QGramExtractor:
    """
    Extracts linguistic and numerical q-grams with boundary padding from normalized strings.
    """

    def __init__(self, q: int = Config.DEFAULT_Q, pad_char: str = "_"):
        """
        Parameters:
        - q: Length of character n-grams (default: 3 for trigrams).
        - pad_char: Boundary padding character (default: '_').
        """
        if q < 1:
            raise ValueError(f"q must be an integer >= 1, received: {q}")
        self.q = q
        self.pad_char = pad_char
        self.pad_len = q - 1

    def pad_token(self, token: str) -> str:
        """
        Applies boundary padding to an individual token.
        Example (q=3): 'tab' -> '__tab__'
        """
        padding = self.pad_char * self.pad_len
        return f"{padding}{token}{padding}"

    def extract_from_token(self, token: str) -> List[str]:
        """
        Extracts q-grams from a single token with boundary padding.
        Example (q=3, token='60mg'):
        Padded: '__60mg__' -> ['__6', '_60', '60m', '0mg', 'mg_', 'g__']
        """
        if not token:
            return []

        padded = self.pad_token(token)
        qgrams = []
        for i in range(len(padded) - self.q + 1):
            qgrams.append(padded[i : i + self.q])
        return qgrams

    def extract_token_qgrams(self, text: str) -> Set[str]:
        """
        Primary Algorithm 1 Method:
        Tokenizes text by whitespace, pads each token, extracts q-grams,
        and returns a deduplicated Set of q-grams.

        Parameters:
        - text: Cleaned and normalized pharmaceutical description string.

        Returns:
        - Set of unique token-level q-grams.
        """
        if not text or not text.strip():
            return set()

        tokens = text.strip().split()
        all_qgrams: Set[str] = set()

        for token in tokens:
            token_qgrams = self.extract_from_token(token)
            all_qgrams.update(token_qgrams)

        return all_qgrams

    def extract_token_qgrams_list(self, text: str) -> List[str]:
        """
        Returns all q-grams as an ordered list (preserving token frequency/duplicates).
        """
        if not text or not text.strip():
            return []

        tokens = text.strip().split()
        qgrams_list: List[str] = []

        for token in tokens:
            qgrams_list.extend(self.extract_from_token(token))

        return qgrams_list

    def extract_global_qgrams(self, text: str) -> Set[str]:
        """
        Extracts q-grams across the entire string globally (treats string as one single sequence).
        Useful for comparative baseline evaluations against traditional PPRL implementations.
        """
        if not text or not text.strip():
            return set()

        padded = f"{self.pad_char * self.pad_len}{text.strip()}{self.pad_char * self.pad_len}"
        global_qgrams: Set[str] = set()
        for i in range(len(padded) - self.q + 1):
            global_qgrams.add(padded[i : i + self.q])
        return global_qgrams

    def extract_composite_qgrams(
        self,
        name: str,
        dosage: Optional[str] = None,
        dosage_form: Optional[str] = None,
        pack_size: Optional[Union[str, int]] = None,
        dosage_weight: int = 6
    ) -> Set[str]:
        """
        Optimal Composite Multi-Attribute Representation for Component 1:
        Record_Filter = BloomFilter( Tag(Name) ∪ Tag(Dosage) ∪ Tag(Dosage Form) ∪ Tag(Pack Size) )

        Priority 1: Multi-hash replication (dosage_weight=6) + explicit numerical isolation (DOSE_NUM_W{w}_{num}).
        Priority 2: Dual-granularity token n-grams (Bigrams q=2 + Trigrams q=3) for drug name.

        Parameters:
        - name: Drug description or molecule name
        - dosage: Numerical strength (e.g. '150mg', '200/50mg', '10mg/ml', 'N/A')
        - dosage_form: Pharmaceutical formulation (e.g. 'Tablet', 'Capsule', 'Oral suspension', 'Test kit')
        - pack_size: Unit count per pack (e.g. '30', '60', '100', '240')
        - dosage_weight: Multi-hash replication factor for dosage to anchor hard negatives against false merges
        """
        composite_tokens: Set[str] = set()

        # 1. Tag(Name): Dual-granularity token n-grams (Bigrams q=2 + Trigrams q=3)
        # Bigrams ensure high recall under typographical noise; Trigrams preserve lexical specificity.
        if name and name.strip():
            tokens = name.strip().split()
            for token in tokens:
                # Bigrams (q=2 with 1 boundary pad)
                padded_q2 = f"_{token}_"
                for i in range(len(padded_q2) - 1):
                    composite_tokens.add(f"NAME_Q2_{padded_q2[i:i+2]}")

                # Trigrams (q=3 with 2 boundary pads)
                padded_q3 = f"__{token}__"
                for i in range(len(padded_q3) - 2):
                    composite_tokens.add(f"NAME_Q3_{padded_q3[i:i+3]}")

        # 2. Tag(Dosage): Domain-tagged trigrams + exact token + explicit numerical token signatures (Priority 1)
        clean_dose = str(dosage).strip() if dosage is not None else ""
        if clean_dose and clean_dose.lower() not in ("n/a", "na", "unknown", "none"):
            dose_tokens = clean_dose.split()
            dose_numbers = re.findall(r'\b\d+\b', clean_dose)

            for w in range(dosage_weight):
                for token in dose_tokens:
                    for qg in self.extract_from_token(token):
                        composite_tokens.add(f"DOSE_W{w}_{qg}")
                composite_tokens.add(f"EXACT_DOSE_W{w}_{clean_dose.replace(' ', '')}")
                for num in dose_numbers:
                    composite_tokens.add(f"DOSE_NUM_W{w}_{num}")
        else:
            for w in range(dosage_weight):
                composite_tokens.add(f"DOSE_W{w}_NA")

        # 3. Tag(Dosage Form): Formulation q-grams + exact token with prefix 'FORM_'
        clean_form = str(dosage_form).strip() if dosage_form is not None else ""
        if clean_form and clean_form.lower() not in ("unknown", "none", "n/a"):
            form_tokens = clean_form.split()
            for token in form_tokens:
                for qg in self.extract_from_token(token):
                    composite_tokens.add(f"FORM_{qg}")
            composite_tokens.add(f"EXACT_FORM_{clean_form.replace(' ', '_')}")

        # 4. Tag(Pack Size): Standardized packaging count with prefix 'PACK_'
        clean_pack = str(pack_size).strip() if pack_size is not None else ""
        if clean_pack and clean_pack.lower() not in ("standard", "unknown", "none", "n/a"):
            composite_tokens.add(f"PACK_{clean_pack}")

        return composite_tokens

    def compare_token_overlap(self, text1: str, text2: str) -> Dict[str, Union[float, int]]:
        """
        Diagnostic helper to evaluate pure q-gram overlap between two strings
        before Bloom filter encoding.
        """
        qg1 = self.extract_token_qgrams(text1)
        qg2 = self.extract_token_qgrams(text2)

        intersection = len(qg1.intersection(qg2))
        total_len = len(qg1) + len(qg2)
        union = len(qg1.union(qg2))

        dice = (2.0 * intersection) / float(total_len) if total_len > 0 else 0.0
        jaccard = float(intersection) / float(union) if union > 0 else 0.0

        return {
            "qgrams_1": len(qg1),
            "qgrams_2": len(qg2),
            "intersection": intersection,
            "dice_similarity": round(dice, 4),
            "jaccard_similarity": round(jaccard, 4)
        }


if __name__ == "__main__":
    from src.preprocessor import TextPreprocessor

    extractor = QGramExtractor(q=3)

    # Test 1: Standard drug description
    raw_desc = "didanosine 200mg videx tablets"
    qgrams = extractor.extract_token_qgrams(raw_desc)

    print("--- QGramExtractor Self-Test ---")
    print(f"Input: '{raw_desc}'")
    print(f"Total Unique Trigrams (q=3): {len(qgrams)}")
    print(f"Sample Trigrams: {sorted(list(qgrams))[:10]}")

    # Test 2: Hard Negative Evaluation (60mg vs 600mg)
    s1 = TextPreprocessor.normalize("Abacavir/Lamivudine 60/30mg, tablets")
    s2 = TextPreprocessor.normalize("Abacavir/Lamivudine 600/300mg, tablets")

    overlap_stats = extractor.compare_token_overlap(s1, s2)
    print("\n--- Hard Negative Resistance Check (60/30mg vs 600/300mg) ---")
    print(f"String 1: '{s1}'")
    print(f"String 2: '{s2}'")
    print(f"Q-gram Intersection: {overlap_stats['intersection']}")
    print(f"Raw Token Dice:      {overlap_stats['dice_similarity']}")
    print(f"Result: Similarity falls below tau=0.85? -> {overlap_stats['dice_similarity'] < 0.85} (Prevents False Merge!)")