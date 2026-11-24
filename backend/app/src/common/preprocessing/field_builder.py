"""Assemble the configured field sets for all linking methods."""

import pandas as pd

from src.common.config import Config, FIELD_SEPARATOR
from src.common.preprocessing.normalizer import normalize as normalize_field, normalize_series


def composite_field_string(description, dosage, dosage_form, pack_size) -> str:
    """Assemble one canonical composite record, in the same order as the frame builder."""
    return FIELD_SEPARATOR.join(map(normalize_field, (description, dosage, dosage_form, pack_size)))


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
    strings = (FIELD_SEPARATOR.join(values) for values in zip(*parts))
    return pd.Series(strings, index=pd.Index(record_ids), dtype=object)
