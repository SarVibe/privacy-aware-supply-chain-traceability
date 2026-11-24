"""Read and write experiment CSVs."""

from collections.abc import Iterable
from pathlib import Path

import pandas as pd


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    """Write columns in DataFrame order and create parent directories."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destination, index=False, encoding="utf-8", lineterminator="\n")


def require_columns(df: pd.DataFrame, required: Iterable[str], *, table: str) -> None:
    if not df.columns.is_unique:
        raise ValueError(f"{table} column names must be unique")
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"{table} is missing required columns: {', '.join(missing)}")


def read_csv(
    path: str | Path, *, encoding: str = "utf-8", as_text: bool = False, round_trip: bool = False
) -> pd.DataFrame:
    """Read CSVs while preserving literal labels and optionally every text value."""
    return pd.read_csv(
        path, encoding=encoding, keep_default_na=False, na_values=[""],
        dtype=str if as_text else None, skip_blank_lines=not as_text,
        float_precision="round_trip" if round_trip else None,
    )
