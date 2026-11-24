"""Load immutable, layered configuration for the research experiments."""

from dataclasses import dataclass, replace
from math import isfinite
from numbers import Real
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
class SweepConfig:
    lengths: tuple[int, ...]
    hashes: tuple[int, ...]
    victim_draws: int
    max_quick_records: int
    overlap: float
    dict_extra_ratio: float
    reid_topk: tuple[int, ...]
    reid_delta: float
    bit_top: int
    degenerate_fill: float
    grid_csv: str
    profile_csv: str
    analysis_directory: str
    analysis_noise: float
    selection_seeds: int
    min_f1: float
    min_privacy_gain: float
    effect_seed: int
    bootstrap_draws: int


@dataclass(frozen=True)
class ResponseSweepConfig:
    bloom_pairs: tuple[tuple[int, int], ...]
    epsilons: tuple[float, ...]
    output_csv: str
    privacy_csv: str


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
    sweep: SweepConfig | None = None
    response_sweep: ResponseSweepConfig | None = None


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


def _profile_settings(directory: Path, name: str, seen: frozenset[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(name, str) or not name.isidentifier() or name == "base":
        raise ValueError("rq_name must be a configuration name such as rq1")
    if name in seen:
        raise ValueError(f"Circular configuration inheritance at {name}")
    profile = _read_yaml(directory / f"{name}.yaml")
    if "extends" in profile:
        parent = _profile_settings(directory, profile.pop("extends"), seen | {name})
        profile = _merge(parent, profile)
    return profile


def _validate_names(section: str, names: tuple[str, ...]) -> None:
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError(f"{section} must contain non-empty column names")
    if len(set(names)) != len(names):
        raise ValueError(f"{section} column names must be unique")


def positive_integer(value: int, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be an integer >= 1")
    return value


def unit_interval(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a number in [0, 1]")
    return float(value)


def validate_epsilon(value: float) -> float:
    """Require a positive privacy budget, with positive infinity for the control."""
    if isinstance(value, bool) or not isinstance(value, Real) or not value > 0:
        raise ValueError("eps must be a positive number or positive infinity")
    return float(value)


def _validate_sweep(sweep: SweepConfig) -> None:
    for name in ("lengths", "hashes", "reid_topk"):
        values = getattr(sweep, name)
        if not values:
            raise ValueError(f"sweep.{name} must be non-empty")
        for value in values:
            positive_integer(value, f"sweep.{name}")
        if len(set(values)) != len(values):
            raise ValueError(f"sweep.{name} must contain unique values")
    for name in ("victim_draws", "max_quick_records", "bit_top", "selection_seeds", "bootstrap_draws"):
        positive_integer(getattr(sweep, name), f"sweep.{name}")
    for name in ("overlap", "reid_delta", "degenerate_fill", "analysis_noise", "min_f1"):
        unit_interval(getattr(sweep, name), f"sweep.{name}")
    if sweep.overlap == 0:
        raise ValueError("sweep.overlap must be positive")
    for name in ("dict_extra_ratio", "min_privacy_gain"):
        value = getattr(sweep, name)
        if type(value) not in (float, int) or not isfinite(value) or value < 0:
            raise ValueError(f"sweep.{name} must be finite and non-negative")
    if type(sweep.effect_seed) is not int or sweep.effect_seed < 0:
        raise ValueError("sweep.effect_seed must be a non-negative integer")
    for name in ("grid_csv", "profile_csv", "analysis_directory"):
        value = getattr(sweep, name)
        if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
            raise ValueError(f"sweep.{name} must be relative to the results directory")


def _validate(cfg: Config) -> None:
    for name, value in (("bloom.l", cfg.bloom.l), ("bloom.k", cfg.bloom.k), ("bloom.q", cfg.bloom.q),
                        ("max_records_per_entity", cfg.max_records_per_entity)):
        positive_integer(value, name)
    if not isinstance(cfg.bloom.pad_char, str) or len(cfg.bloom.pad_char) != 1 or cfg.bloom.pad_char.isalnum():
        raise ValueError("bloom.pad_char must be one non-alphanumeric character")
    try:
        if not bytes.fromhex(cfg.bloom.hmac_key):
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("bloom.hmac_key must be a non-empty hexadecimal string") from None
    grid = cfg.tau_grid
    unit_interval(grid.start, "tau_grid.start")
    unit_interval(grid.stop, "tau_grid.stop")
    if grid.start > grid.stop or type(grid.step) not in (float, int) or not isfinite(grid.step) or grid.step <= 0:
        raise ValueError("tau_grid requires start <= stop and a finite positive step")
    if type(cfg.val_fraction) not in (float, int) or not 0 < cfg.val_fraction < 1:
        raise ValueError("val_fraction must be between 0 and 1 (exclusive)")
    for level in cfg.noise_levels:
        unit_interval(level, "noise_levels")
    if not cfg.noise_levels or len(set(cfg.noise_levels)) != len(cfg.noise_levels):
        raise ValueError("noise_levels must be non-empty and unique")
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
    if cfg.sweep is not None:
        _validate_sweep(cfg.sweep)
    if cfg.response_sweep is not None:
        response = cfg.response_sweep
        if not response.bloom_pairs or len(set(response.bloom_pairs)) != len(response.bloom_pairs):
            raise ValueError("response_sweep.bloom_pairs must contain unique pairs")
        for length, hashes in response.bloom_pairs:
            positive_integer(length, "response_sweep.l")
            positive_integer(hashes, "response_sweep.k")
        if not response.epsilons or len(set(response.epsilons)) != len(response.epsilons):
            raise ValueError("response_sweep.epsilons must be non-empty and unique")
        for epsilon in response.epsilons:
            validate_epsilon(epsilon)
        for path in (response.output_csv, response.privacy_csv):
            if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("response_sweep output paths must be relative to the results directory")


def load_config(rq_name: str, *, config_dir: Path | None = None) -> Config:
    """Load base YAML and recursively apply overrides from the named RQ YAML."""
    directory = config_dir if config_dir is not None else app_dir() / "configs"
    settings = _merge(_read_yaml(directory / "base.yaml"), _profile_settings(directory, rq_name))
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
        if "sweep" in settings:
            sweep = settings["sweep"]
            for name in ("lengths", "hashes", "reid_topk"):
                if not isinstance(sweep[name], list):
                    raise TypeError(f"sweep.{name} must be a YAML list")
                sweep[name] = tuple(sweep[name])
            settings["sweep"] = SweepConfig(**sweep)
        if "response_sweep" in settings:
            response = settings["response_sweep"]
            pairs, budgets = response["bloom_pairs"], response["epsilons"]
            if not isinstance(pairs, list) or any(not isinstance(pair, list) or len(pair) != 2 for pair in pairs):
                raise TypeError("response_sweep.bloom_pairs must be a YAML list of pairs")
            if not isinstance(budgets, list):
                raise TypeError("response_sweep.epsilons must be a YAML list")
            settings["response_sweep"] = ResponseSweepConfig(
                **{**response, "bloom_pairs": tuple(map(tuple, pairs)), "epsilons": tuple(budgets)}
            )
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


def all_fields_noise(cfg: Config) -> Config:
    """Apply the separately versioned noise artifacts to an experiment configuration."""
    variant = load_config("rq1_all_fields")
    return replace(cfg, paths=replace(cfg.paths, noisy=variant.paths.noisy), noise_fields=variant.noise_fields)
