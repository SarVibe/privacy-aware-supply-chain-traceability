"""Canonicalize text for the shared linking field sets."""

import unicodedata

import pandas as pd


def normalize(text: object) -> str:
    """Apply NFKC and case folding, retaining only Unicode letters and digits."""
    if pd.isna(text):
        return ""
    value = str(text)
    while True:
        folded = unicodedata.normalize("NFKC", value).casefold()
        cleaned = "".join(char for char in folded if char.isalpha() or char.isdigit())
        # Removing a separator can expose adjacent characters that compose on the next NFKC pass.
        if cleaned == value:
            return cleaned
        value = cleaned


def normalize_series(series: pd.Series) -> pd.Series:
    """Normalize each value while preserving the index and Series name."""
    return series.map(normalize)
