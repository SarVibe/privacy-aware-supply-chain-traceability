"""Prepare shipment rows and assign the approved clinical product pack IDs."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import numpy as np
import pandas as pd

from src.common.config import Config
from src.common.data.schema import required_columns, validate_frame
from src.common.seeding import make_rng

_EntityKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class PreparationResult:
    """Prepared records, canonical key map and input-to-output counts."""

    records: pd.DataFrame
    entity_map: pd.DataFrame
    input_rows: int
    empty_rows_removed: int
    exact_duplicates: int
    entities_capped: int
    cap_rows_removed: int
    sample_rows_removed: int


def _text_key(value: object) -> str:
    if pd.isna(value):
        return ""
    return " ".join(str(value).casefold().split())


def _pack_key(value: object) -> str:
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"Pack size must be an integer, got {value!r}") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError(f"Pack size must be an integer, got {value!r}")
    return str(int(number))


def _entity_key(molecule: object, dosage: object, form: object, pack: object) -> _EntityKey:
    molecule_key = _text_key(molecule)
    form_key = _text_key(form)
    if not molecule_key or not form_key:
        raise ValueError("Entity keys require non-empty molecule/test type and dosage form")
    return (molecule_key, _text_key(dosage), form_key, _pack_key(pack))


def _source_columns(raw_df: pd.DataFrame, cfg: Config) -> dict[str, str]:
    raw, columns = cfg.raw_columns, cfg.columns
    sources = {
        raw.description: columns.description,
        raw.molecule: columns.molecule,
        raw.dosage: columns.dosage,
        raw.dosage_form: columns.dosage_form,
        raw.pack_size: columns.pack_size,
    }
    if not raw_df.columns.is_unique:
        raise ValueError("Raw table column names must be unique")
    missing = [column for column in sources if column not in raw_df]
    if missing:
        raise ValueError(f"Raw table is missing required columns: {', '.join(missing)}")
    return sources


def prepare_base_data(raw_df: pd.DataFrame, cfg: Config) -> PreparationResult:
    """Build base records, their canonical entity map and preparation counts."""
    sources = _source_columns(raw_df, cfg)
    columns = cfg.columns
    valid_description = raw_df[cfg.raw_columns.description].map(
        lambda value: pd.notna(value) and bool(str(value).strip())
    )
    valid_rows = raw_df.loc[valid_description].reset_index(drop=True)
    exact_duplicates = int(valid_rows.duplicated().sum())
    frame = valid_rows.loc[:, list(sources)].rename(columns=sources)
    if columns.record_id in valid_rows:
        frame[columns.record_id] = valid_rows[columns.record_id]
    else:
        frame[columns.record_id] = [f"R{i:06d}" for i in range(1, len(frame) + 1)]

    key_columns = (columns.molecule, columns.dosage, columns.dosage_form, columns.pack_size)
    keys = [
        _entity_key(*row) for row in frame.loc[:, list(key_columns)].itertuples(index=False, name=None)
    ]
    entity_for_key = {key: f"E{i:04d}" for i, key in enumerate(sorted(set(keys)), start=1)}
    frame[columns.entity_id] = [entity_for_key[key] for key in keys]
    frame = frame.loc[:, list(required_columns(cfg))]
    validate_frame(frame, cfg)

    cap_rng = make_rng(0, "entity_cap")
    retain = np.ones(len(frame), dtype=bool)
    entities_capped = 0
    cap = cfg.max_records_per_entity
    for positions in frame.groupby(columns.entity_id, sort=True).indices.values():
        if len(positions) > cap:
            retain[positions] = False
            retain[cap_rng.choice(positions, size=cap, replace=False)] = True
            entities_capped += 1
    capped = frame.loc[retain]

    selected = capped
    if cfg.sample_entities is not None and cfg.sample_entities < len(entity_for_key):
        sample_rng = make_rng(cfg.sample_entities_seed, "sample_entities")
        picked = sample_rng.choice(list(entity_for_key.values()), size=cfg.sample_entities, replace=False)
        selected = capped.loc[capped[columns.entity_id].isin(picked)]

    counts = selected[columns.entity_id].value_counts()
    entity_map = pd.DataFrame(
        [(entity, *key, int(counts[entity])) for key, entity in entity_for_key.items() if entity in counts],
        columns=[columns.entity_id, *key_columns, "record_count"],
    )
    return PreparationResult(
        records=selected.reset_index(drop=True),
        entity_map=entity_map,
        input_rows=len(raw_df),
        empty_rows_removed=len(raw_df) - len(valid_rows),
        exact_duplicates=exact_duplicates,
        entities_capped=entities_capped,
        cap_rows_removed=len(frame) - len(capped),
        sample_rows_removed=len(capped) - len(selected),
    )


def prepare_base_dataset(raw_df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Prepare a validated base dataset while preserving the retained raw text."""
    return prepare_base_data(raw_df, cfg).records
