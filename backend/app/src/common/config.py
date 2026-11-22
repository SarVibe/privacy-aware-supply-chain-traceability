"""Load immutable, layered configuration for the research experiments."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.common.paths import app_dir


@dataclass(frozen=True)
class PathsConfig:
    raw: str
    raw_filename: str
    prepared: str
    splits: str
    noisy: str
    results: str


@dataclass(frozen=True)
class ColumnsConfig:
    record_id: str
    entity_id: str
    description: str
    molecule: str
    dosage: str
    dosage_form: str
    pack_size: str

    @property
    def text(self) -> tuple[str, ...]:
        """Return the four text inputs shared by the linking methods."""
        return (self.description, self.dosage, self.dosage_form, self.pack_size)


@dataclass(frozen=True)
class RawColumnsConfig:
    description: str
    molecule: str
    dosage: str
    dosage_form: str
    pack_size: str


@dataclass(frozen=True)
class BloomConfig:
    l: int
    k: int
    q: int
    pad_char: str
    hmac_key: str


@dataclass(frozen=True)
class TauGridConfig:
    start: float
    stop: float
    step: float


@dataclass(frozen=True)
class Config:
    paths: PathsConfig
    columns: ColumnsConfig
    raw_columns: RawColumnsConfig
    bloom: BloomConfig
    seeds: tuple[int, ...]
    max_records_per_entity: int
    sample_entities: int | None
    noise_levels: tuple[float, ...]
    typos_per_selected_record: tuple[int, ...]
    noise_fields: tuple[str, ...]
    val_fraction: float
    tau_grid: TauGridConfig
    field_sets: tuple[str, ...]
    methods: tuple[str, ...]
    sample_entities_seed: int = 0


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = base.copy()
    for key, value in override.items():
        original = merged.get(key)
        if isinstance(original, dict) and isinstance(value, dict):
            value = _merge(original, value)
        merged[key] = value
    return merged


def _validate_names(section: str, names: tuple[str, ...]) -> None:
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError(f"{section} must contain non-empty column names")
    if len(set(names)) != len(names):
        raise ValueError(f"{section} column names must be unique")


def _validate(cfg: Config) -> None:
    if type(cfg.bloom.l) is not int or cfg.bloom.l < 1 or cfg.bloom.l & (cfg.bloom.l - 1):
        raise ValueError("bloom.l must be a positive power of two")
    for name, value in (("bloom.k", cfg.bloom.k), ("bloom.q", cfg.bloom.q),
                        ("max_records_per_entity", cfg.max_records_per_entity)):
        if type(value) is not int or value < 1:
            raise ValueError(f"{name} must be an integer >= 1")
    if type(cfg.val_fraction) not in (float, int) or not 0 < cfg.val_fraction < 1:
        raise ValueError("val_fraction must be between 0 and 1 (exclusive)")
    if not cfg.noise_levels or any(
        type(level) not in (float, int) or not 0 <= level <= 1 for level in cfg.noise_levels
    ):
        raise ValueError("noise_levels must be non-empty and contain only values in [0, 1]")
    if not cfg.seeds or len(cfg.seeds) > 10 or any(
        type(seed) is not int or seed < 0 for seed in cfg.seeds
    ) or len(set(cfg.seeds)) != len(cfg.seeds):
        raise ValueError("seeds must contain 1 to 10 unique non-negative integers")
    _validate_names(
        "columns",
        (cfg.columns.record_id, cfg.columns.entity_id, cfg.columns.molecule, *cfg.columns.text),
    )
    _validate_names(
        "raw_columns",
        (cfg.raw_columns.description, cfg.raw_columns.molecule, cfg.raw_columns.dosage,
         cfg.raw_columns.dosage_form, cfg.raw_columns.pack_size),
    )
    if cfg.sample_entities is not None and (
        type(cfg.sample_entities) is not int or cfg.sample_entities < 1
    ):
        raise ValueError("sample_entities must be null or an integer >= 1")
    if type(cfg.sample_entities_seed) is not int or cfg.sample_entities_seed < 0:
        raise ValueError("sample_entities_seed must be a non-negative integer")


def load_config(rq_name: str, *, config_dir: Path | None = None) -> Config:
    """Load base YAML and recursively apply overrides from the named RQ YAML."""
    if not rq_name.isidentifier():
        raise ValueError("rq_name must be a configuration name such as rq1")
    directory = config_dir if config_dir is not None else app_dir() / "configs"
    settings = _merge(_read_yaml(directory / "base.yaml"), _read_yaml(directory / f"{rq_name}.yaml"))
    constructors = {
        "paths": PathsConfig,
        "columns": ColumnsConfig,
        "raw_columns": RawColumnsConfig,
        "bloom": BloomConfig,
        "tau_grid": TauGridConfig,
    }
    try:
        for name, constructor in constructors.items():
            settings[name] = constructor(**settings[name])
        settings.setdefault("sample_entities", None)
        for name in (
            "seeds", "noise_levels", "typos_per_selected_record", "noise_fields", "field_sets", "methods"
        ):
            if not isinstance(settings[name], list):
                raise TypeError(f"{name} must be a YAML list")
            settings[name] = tuple(settings[name])
        cfg = Config(**settings)
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Invalid {rq_name} configuration: {exc}") from exc
    _validate(cfg)
    return cfg
