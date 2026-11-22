"""Assemble the configured field sets for all linking methods."""

import pandas as pd

from src.common.config import Config
from src.common.preprocessing.normalizer import normalize_series

_SEPARATOR = "|"


def build_field_strings(
    df: pd.DataFrame, field_set: str, cfg: Config, normalize: bool
) -> pd.Series:
    """Build raw or normalized field strings indexed by the configured record ID."""
    columns = cfg.columns
    if field_set == "description":
        fields = (columns.description,)
    elif field_set == "composite":
        fields = columns.text
    else:
        raise ValueError(f"Unknown field set: {field_set!r}")

    missing = [column for column in (columns.record_id, *fields) if column not in df]
    if missing:
        raise ValueError(f"Missing required columns for {field_set}: {', '.join(missing)}")
    record_ids = df[columns.record_id]
    if record_ids.isna().any() or not record_ids.is_unique:
        raise ValueError(f"{columns.record_id} must be non-null and unique")

    if normalize:
        parts = [normalize_series(df[field]) for field in fields]
    else:
        parts = [df[field].map(lambda value: "" if pd.isna(value) else str(value)) for field in fields]
    strings = (_SEPARATOR.join(values) for values in zip(*parts))
    return pd.Series(strings, index=pd.Index(record_ids), dtype=object)
