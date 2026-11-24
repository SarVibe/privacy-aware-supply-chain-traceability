"""Dedicated configuration for the RQ2 collision benchmark."""

from dataclasses import dataclass
from itertools import product
from math import isclose
from pathlib import Path

import yaml

from src.common.config import TauGridConfig, positive_integer, unit_interval
from src.common.linking.threshold import threshold_values
from src.common.paths import app_dir


@dataclass(frozen=True)
class Controls:
    positive: tuple[int, int]
    min_lift: float
    permutations: int
    max_random_gap: float


@dataclass(frozen=True)
class Pilot:
    seed: int
    max_entities: int
    reduction_step: float


@dataclass(frozen=True)
class Analysis:
    bootstrap_draws: int
    seed: int
    histogram_bins: int
    f1_budget: float
    h3_relative_reduction: float | None


@dataclass(frozen=True)
class CollisionConfig:
    field_set: str
    seeds: tuple[int, ...]
    gate_seeds: tuple[int, ...]
    split_fractions: tuple[float, float, float]
    primary_noise: float
    robustness_noise: tuple[float, ...]
    all_fields_noise: float
    baseline: tuple[int, int]
    primary_grid: tuple[tuple[int, int], ...]
    extended_grid: tuple[tuple[int, int], ...]
    taus: tuple[float, ...]
    key_env: str
    controls: Controls
    pilot: Pilot
    analysis: Analysis


def _pair(values) -> tuple[int, int]:
    length, hashes = values
    positive_integer(length, "l")
    positive_integer(hashes, "k")
    if hashes > length:
        raise ValueError("k must not exceed l")
    return length, hashes


def _grid(lengths, hashes):
    cells = tuple(_pair(pair) for pair in product(lengths, hashes))
    if not cells or len(cells) != len(set(cells)):
        raise ValueError("Bloom grid must be non-empty and contain unique pairs")
    return cells


def _seeds(values, name):
    seeds = tuple(values)
    if not seeds or len(set(seeds)) != len(seeds) or any(type(seed) is not int or seed < 0 for seed in seeds):
        raise ValueError(f"{name} must contain unique nonnegative integer seeds")
    return seeds


def load_collision_config(path: Path | None = None) -> CollisionConfig:
    source = path if path is not None else app_dir() / "configs" / "rq2_collision.yaml"
    with source.open(encoding="utf-8") as handle:
        settings = yaml.safe_load(handle)
    try:
        settings["seeds"] = _seeds(settings["seeds"], "seeds")
        settings["gate_seeds"] = _seeds(settings["gate_seeds"], "gate_seeds")
        settings["split_fractions"] = tuple(settings["split_fractions"])
        settings["robustness_noise"] = tuple(settings["robustness_noise"])
        settings["baseline"] = _pair(settings["baseline"])
        for name in ("primary_grid", "extended_grid"):
            settings[name] = _grid(**settings[name])
        settings["taus"] = threshold_values(TauGridConfig(**settings.pop("tau_grid")))
        settings["controls"]["positive"] = _pair(settings["controls"]["positive"])
        settings["controls"] = Controls(**settings["controls"])
        settings["pilot"] = Pilot(**settings["pilot"])
        settings["analysis"] = Analysis(**settings["analysis"])
        cfg = CollisionConfig(**settings)
    except (AttributeError, KeyError, TypeError) as exc:
        raise ValueError(f"Invalid collision configuration: {source}") from exc

    if cfg.field_set != "composite":
        raise ValueError("The collision benchmark requires the composite field set")
    if not set(cfg.seeds).issubset(cfg.gate_seeds) or cfg.pilot.seed not in cfg.seeds:
        raise ValueError("Main seeds must be gate seeds and the pilot seed must be a main seed")
    fractions = cfg.split_fractions
    if len(fractions) != 3 or any(not 0 < f < 1 for f in fractions) or not isclose(sum(fractions), 1.0):
        raise ValueError("Validation, test and reference fractions must be positive and sum to one")
    levels = (cfg.primary_noise, *cfg.robustness_noise)
    for level in (*levels, cfg.all_fields_noise):
        unit_interval(level, "noise")
    if len(set(levels)) != len(levels):
        raise ValueError("Primary and robustness noise levels must differ")
    if not cfg.taus or not all(0 < tau <= 1 for tau in cfg.taus):
        raise ValueError("tau must be in (0, 1]")
    if cfg.baseline not in cfg.primary_grid or cfg.baseline not in cfg.extended_grid:
        raise ValueError("Baseline must occur in both grids")
    if not isinstance(cfg.key_env, str) or not cfg.key_env.isidentifier():
        raise ValueError("key_env must name an environment variable")
    for value, label in ((cfg.controls.permutations, "permutations"), (cfg.pilot.max_entities, "max_entities"),
                         (cfg.analysis.bootstrap_draws, "bootstrap_draws"), (cfg.analysis.histogram_bins, "histogram_bins")):
        positive_integer(value, label)
    if cfg.pilot.max_entities < 3 or not cfg.controls.min_lift > 1:
        raise ValueError("Pilot needs at least three entities and the positive-control lift must exceed one")
    unit_interval(cfg.pilot.reduction_step, "reduction_step")
    if cfg.pilot.reduction_step == 0:
        raise ValueError("Pilot reduction step must be positive")
    unit_interval(cfg.controls.max_random_gap, "max_random_gap")
    unit_interval(cfg.analysis.f1_budget, "f1_budget")
    if cfg.analysis.h3_relative_reduction is not None:
        unit_interval(cfg.analysis.h3_relative_reduction, "h3_relative_reduction")
    _seeds((cfg.analysis.seed,), "analysis seed")
    return cfg
