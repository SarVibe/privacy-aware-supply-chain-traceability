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


def partition_reference_entities(
    entity_ids: Iterable[str], validation_fraction: float, test_fraction: float, rng: Generator
) -> dict[str, list[str]]:
    """Allocate a third partition from the IDs held out of validation."""
    if not 0 < test_fraction < 1 - validation_fraction:
        raise ValueError("A positive entity share must remain for the reference partition")
    split = split_entities(entity_ids, validation_fraction, rng)
    held_out = split["test"]
    if len(held_out) < 2 or not split["validation"]:
        raise ValueError("Need at least one entity in validation, test and reference")
    n_test = round((len(held_out) + len(split["validation"])) * test_fraction)
    n_test = min(len(held_out) - 1, max(1, n_test))
    return {"validation": split["validation"], "test": held_out[:n_test], "reference": held_out[n_test:]}


def apply_reference_partition(df: pd.DataFrame, split: dict[str, list[str]], cfg: Config) -> dict[str, pd.DataFrame]:
    """Validate full entity coverage and preserve source row order in three partitions."""
    if set(split) != {"validation", "test", "reference"}:
        raise ValueError("Expected validation, test and reference partitions")
    analysis, reference = apply_split(
        df, {"validation": split["validation"] + split["test"], "test": split["reference"]}, cfg
    )
    validation, test = apply_split(analysis, {name: split[name] for name in _SPLIT_NAMES}, cfg)
    if validation.empty or test.empty or reference.empty:
        raise ValueError("All three partitions must contain records")
    return {"validation": validation, "test": test, "reference": reference}


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


def limit_split(
    validation: pd.DataFrame, test: pd.DataFrame, max_records: int, entity_column: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Bound a split by whole groups, retaining row order in both partitions."""
    if type(max_records) is not int or max_records < 2:
        raise ValueError("max_records must be an integer >= 2")
    total = len(validation) + len(test)
    if total <= max_records:
        return validation, test
    validation_limit = min(max_records - 1, max(1, round(max_records * len(validation) / total)))
    selected = []
    for frame, remaining in ((validation, validation_limit), (test, max_records - validation_limit)):
        entities = []
        for entity, size in frame.groupby(entity_column, sort=True).size().items():
            if size <= remaining:
                entities.append(entity)
                remaining -= size
        if not entities:
            raise ValueError("Record limit leaves an empty split. Increase max_records.")
        selected.append(frame.loc[frame[entity_column].isin(entities)])
    return selected[0], selected[1]


def save_split(split: dict[str, list[str]], path: Path) -> None:
    """Validate and save a split as UTF-8 JSON."""
    _check_split(split)
    path.write_text(json.dumps(split, indent=2) + "\n", encoding="utf-8")


def load_split(path: Path) -> dict[str, list[str]]:
    """Load and validate a saved split."""
    split = json.loads(path.read_text(encoding="utf-8"))
    _check_split(split)
    return split
