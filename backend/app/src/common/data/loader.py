"""Read shipment CSVs without modifying text values."""

from math import isclose
from pathlib import Path

from pandas import DataFrame, read_csv

from src.common.config import Config, load_config
from src.common.data.schema import validate_frame
from src.common.paths import noisy_dir, prepared_dir, raw_csv_path

BASE_DATASET_FILENAME = "base_dataset.csv"
ENTITY_MAP_FILENAME = "entity_map.csv"


def _read_csv(path: Path, encoding: str = "utf-8") -> DataFrame:
    return read_csv(
        path, dtype=str, encoding=encoding, keep_default_na=False, na_values=[""], skip_blank_lines=False
    )


def read_raw_csv(cfg: Config) -> DataFrame:
    """Read the original shipment file as text, treating empty cells as missing."""
    path = raw_csv_path(cfg)
    try:
        return _read_csv(path)
    except UnicodeDecodeError:
        return _read_csv(path, encoding="iso-8859-1")


def read_prepared_csv(cfg: Config) -> DataFrame:
    """Read and validate the prepared base dataset."""
    df = _read_csv(prepared_dir(cfg) / BASE_DATASET_FILENAME)
    validate_frame(df, cfg)
    return df


def read_noisy_csv(path: Path, cfg: Config) -> DataFrame:
    """Read and validate a noisy record CSV."""
    df = _read_csv(path)
    validate_frame(df, cfg)
    return df


def noisy_csv_path(seed: int, level: float, cfg: Config) -> Path:
    """Return the artifact path for a positive whole-percent noise level."""
    if not 0 < level <= 1:
        raise ValueError("A noisy CSV requires a level in (0, 1]")
    percent = round(level * 100)
    if percent == 0 or not isclose(level, percent / 100, rel_tol=0, abs_tol=1e-12):
        raise ValueError("Noisy CSV filenames require a whole-percent noise level")
    return noisy_dir(cfg) / f"seed{seed}" / f"noise_{percent:02d}.csv"


def load_noisy(seed: int, level: float, cfg: Config | None = None) -> DataFrame:
    """Load the base control at level zero or a seed-specific noisy dataset."""
    cfg = cfg if cfg is not None else load_config("rq1")
    if level == 0:
        return read_prepared_csv(cfg)
    return read_noisy_csv(noisy_csv_path(seed, level, cfg), cfg)
