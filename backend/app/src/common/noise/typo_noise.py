"""Inject reproducible record-level typos while protecting numeric text."""

from collections.abc import Sequence
from string import ascii_lowercase

import pandas as pd
from numpy.random import Generator

_KINDS = ("substitute", "delete", "insert", "transpose")
_LOG_COLUMNS = ("record_id", "field", "n_typos", "typo_kinds", "original", "mutated", "skipped_reason")
_NUMERIC_SEPARATORS = "./,:+-"


def _protected(text: str) -> list[bool]:
    digits = [char.isdigit() for char in text]
    return [
        digit or (
            0 < i < len(text) - 1
            and digits[i - 1] and digits[i + 1]
            and (char in _NUMERIC_SEPARATORS or char.isspace())
        )
        for i, (char, digit) in enumerate(zip(text, digits))
    ]


def _positions(text: str, protected: list[bool], kind: str) -> list[int]:
    if kind == "insert":
        return [
            i for i in range(len(text) + 1)
            if not (0 < i < len(text) and protected[i - 1] and protected[i])
        ]
    if kind == "transpose":
        return [
            i for i in range(len(text) - 1)
            if not (protected[i] or protected[i + 1]) and text[i] != text[i + 1]
        ]
    return [i for i, is_protected in enumerate(protected) if not is_protected]


def _candidate(text: str, index: int, kind: str, rng: Generator, avoid: str | None) -> str:
    prefix = text[:index]
    if kind == "delete":
        return prefix + text[index + 1:]
    if kind == "transpose":
        return prefix + text[index + 1] + text[index] + text[index + 2:]
    suffix = text[index:] if kind == "insert" else text[index + 1:]
    alphabet = ascii_lowercase if kind == "insert" else ascii_lowercase.replace(text[index], "")
    if avoid is not None and len(avoid) == len(prefix) + 1 + len(suffix):
        if avoid.startswith(prefix) and avoid.endswith(suffix):
            alphabet = alphabet.replace(avoid[index], "")
    return prefix + alphabet[rng.integers(len(alphabet))] + suffix


def _choose_typo(
    text: str,
    rng: Generator,
    kinds: Sequence[str],
    *,
    avoid: str | None = None,
    needs_next: bool = False,
) -> tuple[str, str]:
    protected = _protected(text)
    if all(protected):
        return text, ""
    for kind in rng.permutation(kinds).tolist():
        for index in rng.permutation(_positions(text, protected, kind)).tolist():
            mutated = _candidate(text, index, kind, rng, avoid)
            if mutated != avoid and (not needs_next or not all(_protected(mutated))):
                return mutated, kind
    return text, ""


def apply_typo(text: str, rng: Generator, kind: str) -> str:
    """Apply one typo of the requested kind, or return text if no position is valid."""
    if kind not in _KINDS:
        raise ValueError(f"Unknown typo kind: {kind!r}")
    return _choose_typo(text, rng, (kind,))[0]


def _mutate_field(
    original: object, n_requested: int, min_length: int, rng: Generator
) -> tuple[object, list[str], str]:
    if not isinstance(original, str):
        return original, [], "missing_text" if pd.isna(original) else "non_text"
    if len(original) < min_length:
        return original, [], "short_text"
    mutated, kinds = original, []
    for edit in range(n_requested):
        mutated, kind = _choose_typo(
            mutated, rng, _KINDS, avoid=original, needs_next=edit + 1 < n_requested
        )
        if not kind:
            return original, [], "no_valid_typo"
        kinds.append(kind)
    return mutated, kinds, ""


def inject_noise(
    df: pd.DataFrame,
    noise_level: float,
    fields: Sequence[str],
    typos_range: Sequence[int],
    rng: Generator,
    min_length: int = 3,
    *,
    record_id_column: str = "record_id",
    entity_id_column: str = "entity_id",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sample records without replacement and log each selected field's edits."""
    if not 0 <= noise_level <= 1:
        raise ValueError("noise_level must be in [0, 1]")
    if noise_level == 0:
        return df, pd.DataFrame(columns=_LOG_COLUMNS)
    if len(typos_range) != 2 or any(type(value) is not int for value in typos_range):
        raise ValueError("typos_range must contain two integer bounds")
    low, high = typos_range
    if not 1 <= low <= high <= 2:
        raise ValueError("typos_range must have inclusive bounds between 1 and 2")
    if type(min_length) is not int or min_length < 0:
        raise ValueError("min_length must be a non-negative integer")
    if not fields or len(set(fields)) != len(fields):
        raise ValueError("fields must contain unique noise columns")
    if {record_id_column, entity_id_column}.intersection(fields):
        raise ValueError("Record and entity ID columns cannot receive noise")
    if not df.columns.is_unique:
        raise ValueError("Record table column names must be unique")
    missing = [column for column in (record_id_column, *fields) if column not in df]
    if missing:
        raise ValueError(f"Record table is missing columns: {', '.join(missing)}")
    record_ids = df[record_id_column]
    if not record_ids.is_unique or record_ids.isna().any():
        raise ValueError(f"{record_id_column} must be non-null and unique")

    noisy = df.copy()
    log_rows = []
    field_indexes = [(field, df.columns.get_loc(field)) for field in fields]
    selected = rng.choice(len(df), size=round(noise_level * len(df)), replace=False)
    for row in selected.tolist():
        n_requested = int(rng.integers(low, high + 1))
        for field, col in field_indexes:
            original = df.iat[row, col]
            mutated, kinds, reason = _mutate_field(original, n_requested, min_length, rng)
            if kinds:
                noisy.iat[row, col] = mutated
            log_rows.append(
                (record_ids.iat[row], field, len(kinds), "|".join(kinds), original, mutated, reason)
            )
    return noisy, pd.DataFrame(log_rows, columns=_LOG_COLUMNS)
