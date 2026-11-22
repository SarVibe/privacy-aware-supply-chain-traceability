"""Read and write experiment CSVs."""

from pathlib import Path

import pandas as pd


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    """Write columns in DataFrame order and create parent directories."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destination, index=False, encoding="utf-8", lineterminator="\n")


def read_csv(path: str | Path) -> pd.DataFrame:
    """Read an experiment CSV, preserving literal labels such as 'none'."""
    return pd.read_csv(path, encoding="utf-8", keep_default_na=False, na_values=[""])
