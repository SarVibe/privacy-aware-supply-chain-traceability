"""Create, apply and persist entity-disjoint validation and test splits."""

import json
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
from numpy.random import Generator

from src.common.config import Config, load_config

_SPLIT_NAMES = ("validation", "test")


def split_entities(
    entity_ids: Iterable[str], val_fraction: float, rng: Generator
) -> dict[str, list[str]]:
    """Shuffle unique IDs and allocate the rounded validation share."""
    if not 0 < val_fraction < 1:
        raise ValueError("val_fraction must be between 0 and 1 (exclusive)")
    ids = list(entity_ids)
    if any(not isinstance(entity, str) or not entity for entity in ids):
        raise ValueError("entity_ids must contain non-empty strings")
    shuffled = sorted(set(ids))
    rng.shuffle(shuffled)
    n_validation = round(len(shuffled) * val_fraction)
    if len(shuffled) >= 2:
        n_validation = min(len(shuffled) - 1, max(1, n_validation))
    else:
        n_validation = 0
    return {"validation": shuffled[:n_validation], "test": shuffled[n_validation:]}


def _check_split(split: dict[str, list[str]]) -> tuple[set[str], set[str]]:
    if not isinstance(split, dict) or set(split) != set(_SPLIT_NAMES):
        raise ValueError("A split must contain exactly 'validation' and 'test'")
    for name in _SPLIT_NAMES:
        ids = split[name]
        if not isinstance(ids, list) or any(not isinstance(entity, str) or not entity for entity in ids):
            raise ValueError(f"{name} must be a list of non-empty entity IDs")
        if len(ids) != len(set(ids)):
            raise ValueError(f"{name} contains duplicate entity IDs")
    validation, test = set(split["validation"]), set(split["test"])
    if validation & test:
        raise ValueError("Validation and test contain overlapping entity IDs")
    return validation, test


def apply_split(
    df: pd.DataFrame, split: dict[str, list[str]], cfg: Config | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return validation and test records using the configured entity ID column."""
    validation, test = _check_split(split)
    column = (cfg if cfg is not None else load_config("rq1")).columns.entity_id
    if column not in df:
        raise ValueError(f"Record table is missing the entity ID column: {column}")
    entity_ids = df[column]
    if set(entity_ids) != validation | test:
        raise ValueError("Split entity IDs must exactly cover the record table")
    return df.loc[entity_ids.isin(validation)].copy(), df.loc[entity_ids.isin(test)].copy()


def save_split(split: dict[str, list[str]], path: Path) -> None:
    """Validate and save a split as UTF-8 JSON."""
    _check_split(split)
    path.write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")


def load_split(path: Path) -> dict[str, list[str]]:
    """Load and validate a saved split."""
    split = json.loads(path.read_text(encoding="utf-8"))
    _check_split(split)
    return split
