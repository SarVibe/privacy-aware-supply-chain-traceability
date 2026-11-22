import pandas as pd
import pytest

from src.common.preprocessing.normalizer import normalize, normalize_series


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Paracetamol-500mg", "paracetamol500mg"),
        ("paracetamol 500 mg", "paracetamol500mg"),
        ("PARACETAMOL_500MG", "paracetamol500mg"),
        (None, ""),
        (float("nan"), ""),
        (pd.NA, ""),
        ("", ""),
        ("ＣＡＦÉ Straße—漢字 １２٣", "caféstrasse漢字12٣"),
        ("A\u00a0b.09", "ab09"),
        ("ᄀ-ᅡ", "가"),
    ],
)
def test_normalizes_and_is_idempotent(text, expected):
    result = normalize(text)
    assert result == expected
    assert normalize(result) == result


def test_series_normalizes_missing_values_and_preserves_index_and_name():
    series = pd.Series(["Tablet-20MG", None, " É "], index=["r3", "r1", "r2"], name="description")
    expected = pd.Series(["tablet20mg", "", "é"], index=series.index, name=series.name)
    pd.testing.assert_series_equal(normalize_series(series), expected)
