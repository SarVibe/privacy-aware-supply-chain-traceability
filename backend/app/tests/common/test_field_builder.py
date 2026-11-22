from dataclasses import replace

import pandas as pd
import pytest

from src.common.config import load_config
from src.common.preprocessing.field_builder import build_field_strings


@pytest.fixture
def records():
    return pd.DataFrame(
        {
            "pack_size": ["030", 60],
            "dosage_form": [" Coated Tablet ", pd.NA],
            "raw_item_description": [" A|B-500MG ", None],
            "record_id": ["R2", "R1"],
            "dosage": ["500 MG", float("nan")],
        },
        index=[11, 5],
    )


@pytest.mark.parametrize(
    ("field_set", "normalize", "expected"),
    [
        ("description", False, [" A|B-500MG ", ""]),
        ("description", True, ["ab500mg", ""]),
        ("composite", False, [" A|B-500MG |500 MG| Coated Tablet |030", "|||60"]),
        ("composite", True, ["ab500mg|500mg|coatedtablet|030", "|||60"]),
    ],
)
def test_field_order_missing_values_and_separator(records, field_set, normalize, expected):
    result = build_field_strings(records, field_set, load_config("rq1"), normalize)
    expected_index = pd.Index(["R2", "R1"], name="record_id")
    pd.testing.assert_series_equal(result, pd.Series(expected, index=expected_index))


def test_uses_configured_columns_and_description_needs_no_structured_fields():
    cfg = load_config("rq1")
    cfg = replace(cfg, columns=replace(cfg.columns, record_id="row_key", description="item"))
    df = pd.DataFrame({"row_key": [17, 2], "item": [" A-1 ", "B"]})
    result = build_field_strings(df, "description", cfg, normalize=True)
    pd.testing.assert_series_equal(result, pd.Series(["a1", "b"], index=pd.Index([17, 2], name="row_key")))


def test_missing_required_columns_raise_clear_error(records):
    cfg = load_config("rq1")
    with pytest.raises(ValueError, match="Missing required columns.*dosage"):
        build_field_strings(records.drop(columns="dosage"), "composite", cfg, normalize=False)
