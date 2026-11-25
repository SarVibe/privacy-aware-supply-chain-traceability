"""Load the frozen v2 profile independently of the v1 and RQ3 profiles."""

import hmac
import os
from dataclasses import dataclass
from itertools import product
from math import isclose, isfinite

import yaml

from src.common.config import TauGridConfig, positive_integer, unit_interval
from src.common.linking.threshold import threshold_values
from src.common.paths import app_dir
from src.rq2.collision_config import Analysis

PROFILE = app_dir() / "configs" / "rq2_collision_v2.yaml"


@dataclass(frozen=True)
class V2Control:
    positive: tuple[int, int]
    min_matched_lift: float
    random_trials: int
    max_random_gap: float


@dataclass(frozen=True)
class V2Pilot:
    seed: int
    max_entities: int


@dataclass(frozen=True)
class V2Protocol:
    field_set: str
    seeds: tuple[int, ...]
    split_fractions: tuple[float, ...]
    primary_noise: float
    robustness_noise: tuple[float, ...]
    all_fields_noise: float
    baseline: tuple[int, int]
    grid: tuple[tuple[int, int], ...]
    taus: tuple[float, ...]
    sensitivity_taus: tuple[float, ...]
    key_env: str
    controls: V2Control
    pilot: V2Pilot
    analysis: Analysis


def load_v2_protocol() -> V2Protocol:
    settings = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    axes = settings["grid"]
    settings["grid"] = tuple(product(axes["lengths"], axes["hashes"]))
    settings["taus"] = threshold_values(TauGridConfig(**settings.pop("tau_grid")))
    for name in ("seeds", "split_fractions", "robustness_noise", "baseline", "sensitivity_taus"):
        settings[name] = tuple(settings[name])
    control = settings["controls"]
    settings["controls"] = V2Control(**{**control, "positive": tuple(control["positive"])})
    settings["analysis"] = Analysis(**settings["analysis"])
    settings["pilot"] = V2Pilot(**settings["pilot"])
    cfg = V2Protocol(**settings)
    if cfg.field_set != "composite" or set(cfg.seeds) != set(range(5, 10)) or len(cfg.seeds) != 5:
        raise ValueError("V2 requires the composite field and exactly seeds 5–9")
    if cfg.pilot.seed in cfg.seeds or cfg.pilot.seed < 10 or cfg.pilot.max_entities < 3:
        raise ValueError("V2 pilot requires a separate seed and at least three entities")
    if (len(cfg.split_fractions) != 3 or any(not 0 < fraction < 1 for fraction in cfg.split_fractions)
            or not isclose(sum(cfg.split_fractions), 1.0)):
        raise ValueError("V2 split fractions must be positive and sum to one")
    if not cfg.grid or cfg.baseline not in cfg.grid or len(cfg.grid) != len(set(cfg.grid)):
        raise ValueError("V2 requires a unique grid containing Baseline 2")
    for l, k in (*cfg.grid, cfg.controls.positive):
        positive_integer(l, "l")
        positive_integer(k, "k")
        if k > l:
            raise ValueError("Expected 1 <= k <= l")
    for name in ("primary_noise", "all_fields_noise"):
        unit_interval(getattr(cfg, name), name)
    for level in cfg.robustness_noise:
        unit_interval(level, "robustness noise")
    if len({cfg.primary_noise, *cfg.robustness_noise}) != len(cfg.robustness_noise) + 1:
        raise ValueError("Description noise levels must be unique")
    if (not cfg.taus or not cfg.sensitivity_taus or cfg.taus[0] <= 0
            or tuple(sorted(set(cfg.sensitivity_taus))) != cfg.sensitivity_taus
            or any(not cfg.taus[-1] < tau <= 1 for tau in cfg.sensitivity_taus)):
        raise ValueError("V2 sensitivity cutoffs must exceed the primary ceiling and be <= 1")
    for name in ("f1_budget", "h3_relative_reduction"):
        unit_interval(getattr(cfg.analysis, name), name)
    unit_interval(cfg.controls.max_random_gap, "max_random_gap")
    positive_integer(cfg.controls.random_trials, "random_trials")
    positive_integer(cfg.analysis.bootstrap_draws, "bootstrap_draws")
    positive_integer(cfg.analysis.histogram_bins, "histogram_bins")
    if not isfinite(cfg.controls.min_matched_lift) or cfg.controls.min_matched_lift <= 1:
        raise ValueError("Required positive-control lift must exceed one")
    return cfg


def research_root(cfg: V2Protocol, fixture_key: str) -> bytes:
    try:
        key = bytes.fromhex(os.environ.get(cfg.key_env, ""))
    except ValueError:
        key = b""
    if len(key) < 32 or key == bytes.fromhex(fixture_key):
        raise ValueError(f"Supply at least 32 private bytes as hex in {cfg.key_env}")
    return key


def v2_keys(root: bytes, seed: int) -> tuple[bytes, bytes]:
    return tuple(hmac.digest(root, f"rq2:v2:{role}:{seed}".encode("ascii"), "sha256") for role in ("bloom", "exact"))
