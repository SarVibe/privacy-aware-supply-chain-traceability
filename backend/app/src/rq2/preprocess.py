"""Step 1 of the C1 pipeline: standardize raw text (case, spacing, punctuation)."""
import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize(text) -> str:
    """'Paracetamol-500mg' / 'paracetamol 500 mg' / 'PARACETAMOL_500MG' -> 'paracetamol500mg'."""
    if text is None:
        return ""
    t = unicodedata.normalize("NFKD", str(text)).lower()
    return _NON_ALNUM.sub("", t)
