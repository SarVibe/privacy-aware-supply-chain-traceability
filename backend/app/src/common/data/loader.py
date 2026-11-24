"""Read shipment CSVs without modifying text values."""

from dataclasses import dataclass
from math import isclose
from pathlib import Path

from pandas import DataFrame

from src.common.config import Config, load_config
from src.common.data.schema import validate_frame
from src.common.data.splitting import apply_split, limit_split, load_split
from src.common.experiment.io import read_csv
from src.common.paths import noisy_dir, prepared_dir, raw_csv_path, splits_dir

BASE_DATASET_FILENAME = "base_dataset.csv"
ENTITY_MAP_FILENAME = "entity_map.csv"


@dataclass(frozen=True)
class LinkageData:
    config: Config
    field_set: str
    clean: DataFrame
    noisy: DataFrame
    validation: DataFrame
    test: DataFrame


def _read_csv(path: Path, encoding: str = "utf-8") -> DataFrame:
    return read_csv(path, encoding=encoding, as_text=True)


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


def align_noisy_records(clean: DataFrame, noisy: DataFrame, cfg: Config) -> DataFrame:
    """Align observations by stable record ID and verify the ground truth."""
    validate_frame(clean, cfg)
    validate_frame(noisy, cfg)
    rid, eid = cfg.columns.record_id, cfg.columns.entity_id
    left, right = clean.set_index(rid), noisy.set_index(rid)
    if len(left) != len(right) or not left.index.isin(right.index).all():
        raise ValueError("Clean and noisy datasets must contain the same record IDs")
    aligned = right.reindex(left.index)
    if not aligned[eid].equals(left[eid]):
        raise ValueError("Clean and noisy datasets must contain the same entity IDs per record")
    return aligned.reset_index()[noisy.columns]


def load_linkage_data(
    cfg: Config, seed: int, noise: float, field_set: str, *, max_records: int | None = None
) -> LinkageData:
    """Load the paired record artifacts and their saved entity-disjoint split."""
    rid, eid = cfg.columns.record_id, cfg.columns.entity_id
    clean = load_noisy(seed, 0, cfg)
    noisy = align_noisy_records(clean, load_noisy(seed, noise, cfg), cfg)
    split = load_split(splits_dir(cfg) / f"split_seed{seed}.json")
    validation, test = apply_split(noisy, split, cfg)
    if max_records is not None:
        validation, test = limit_split(validation, test, max_records, eid)
        keep = set(validation[rid]) | set(test[rid])
        clean, noisy = clean.loc[clean[rid].isin(keep)], noisy.loc[noisy[rid].isin(keep)]
    if validation.empty or test.empty:
        raise ValueError("Record linkage requires non-empty validation and test splits")
    return LinkageData(cfg, field_set, clean, noisy, validation, test)
