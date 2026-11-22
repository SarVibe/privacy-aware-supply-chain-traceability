"""Validation for prepared record tables and their noisy derivatives."""

from pandas import DataFrame

from src.common.config import Config


def required_columns(cfg: Config) -> tuple[str, ...]:
    """Return the configured identity and linking columns."""
    return (cfg.columns.record_id, cfg.columns.entity_id, *cfg.columns.text)


def validate_frame(df: DataFrame, cfg: Config) -> None:
    """Raise ValueError for missing columns, invalid record IDs or missing truth."""
    if not df.columns.is_unique:
        raise ValueError("Record table column names must be unique")
    missing = [column for column in required_columns(cfg) if column not in df]
    if missing:
        raise ValueError(f"Record table is missing required columns: {', '.join(missing)}")
    record_ids = df[cfg.columns.record_id]
    if record_ids.isna().any() or not record_ids.is_unique:
        raise ValueError(f"{cfg.columns.record_id} must be non-null and unique")
    if df[cfg.columns.entity_id].isna().any():
        raise ValueError(f"{cfg.columns.entity_id} must be non-null")
