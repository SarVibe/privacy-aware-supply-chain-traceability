"""Tune RQ1 thresholds on validation entities and score held-out test entities."""

import argparse
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from experiments.rq1.posthoc import (
    ANALYSES, POST_HOC_TITLE, post_hoc_destination, protect_frozen_results, tune_blocked_tau,
)
from experiments.rq1.rq1_methods import build_bloom_linker, build_exact_linkers
from src.common.config import Config, load_config
from src.common.data.loader import align_noisy_records, load_noisy
from src.common.data.splitting import apply_split, load_split, save_split, split_entities
from src.common.evaluation.metrics import evaluate_clusters
from src.common.experiment.io import write_csv
from src.common.experiment.runner import RunRecorder, iter_grid, timed
from src.common.experiment_metadata import write_metadata
from src.common.linking.base import Linker
from src.common.linking.bloom_blocked import BLOOM_BLOCKED, DESCRIPTION, BloomBlockedLinker, blocking_fields
from src.common.linking.threshold import select_per_noise_tau, select_single_tau, tune_tau
from src.common.linking.threshold import threshold_values as _thresholds
from src.common.paths import results_dir, splits_dir
from src.common.seeding import make_rng

RAW_COLUMNS = (
    "run_id", "seed", "noise_level", "method", "field_set", "tau", "tau_mode", "split",
    "precision", "recall", "f1", "fragmentation_rate", "n_records", "n_entities",
    "n_pred_clusters", "runtime_sec",
)
TAU_COLUMNS = ("seed", "field_set", "noise_level", "tau", "precision", "recall", "f1")
_SMOKE_SEED = 0
_SMOKE_MAX_ENTITIES = 300


def _destination(cfg: Config, out_dir: Path | None, smoke: bool) -> Path:
    regular = results_dir(cfg, "rq1")
    if not smoke:
        return regular if out_dir is None else out_dir.resolve()
    smoke_dir = regular / "smoke"
    if smoke_dir.resolve() != smoke_dir or (out_dir is not None and out_dir.resolve() != smoke_dir):
        raise ValueError("--smoke writes only to results/rq1/smoke")
    return smoke_dir


def _sample_for_smoke(base: pd.DataFrame, cfg: Config) -> set[str] | None:
    entities = sorted(base[cfg.columns.entity_id].unique())
    if cfg.sample_entities is not None or len(entities) <= _SMOKE_MAX_ENTITIES:
        return None
    rng = make_rng(_SMOKE_SEED, "rq1_smoke_entities")
    return set(rng.choice(entities, size=_SMOKE_MAX_ENTITIES, replace=False).tolist())


def _evaluate_test(
    test: pd.DataFrame,
    cfg: Config,
    field_set: str,
    seed: int,
    noise_level: float,
    single_tau: float,
    per_noise_tau: float,
    recorder: RunRecorder,
) -> None:
    methods = (
        *((linker, "none", float("nan")) for linker in build_exact_linkers(cfg, field_set)),
        (build_bloom_linker(cfg, field_set, single_tau), "single", single_tau),
        (build_bloom_linker(cfg, field_set, per_noise_tau), "per_noise", per_noise_tau),
    )
    _record_test(test, cfg, field_set, seed, noise_level, methods, recorder)


def _record_test(
    test: pd.DataFrame, cfg: Config, field_set: str, seed: int, noise_level: float,
    methods: Sequence[tuple[Linker, str, float]], recorder: RunRecorder,
) -> None:
    rid, eid = cfg.columns.record_id, cfg.columns.entity_id
    truth = test.set_index(rid)[eid]
    features = test.drop(columns=eid)
    for linker, mode, tau in methods:
        with timed() as elapsed:
            labels = linker.link(features)
        recorder.add({
            "run_id": f"seed{seed}_n{round(noise_level * 100):02d}_{field_set}_{linker.name}_{mode}",
            "seed": seed,
            "noise_level": noise_level,
            "method": linker.name,
            "field_set": field_set,
            "tau": tau,
            "tau_mode": mode,
            "split": "test",
            **evaluate_clusters(truth, labels),
            "runtime_sec": elapsed(),
        })


def run_experiment(
    cfg: Config,
    *,
    seeds: Sequence[int] | None = None,
    noise_levels: Sequence[float] | None = None,
    out_dir: Path | None = None,
    smoke: bool = False,
    post_hoc: str | None = None,
    val_fraction: float | None = None,
) -> Path:
    """Run the selected seeds and noise levels, returning the artifact directory."""
    chosen_seeds = tuple(cfg.seeds if seeds is None else seeds)
    if smoke:
        if seeds is not None and chosen_seeds != (_SMOKE_SEED,):
            raise ValueError("--smoke uses seed 0 only")
        chosen_seeds = (_SMOKE_SEED,)
    levels = tuple(cfg.noise_levels if noise_levels is None else noise_levels)
    if not chosen_seeds or len(set(chosen_seeds)) != len(chosen_seeds) or not set(chosen_seeds) <= set(cfg.seeds):
        raise ValueError("Choose one or more unique configured seeds")
    if not levels or len(set(levels)) != len(levels) or not set(levels) <= set(cfg.noise_levels):
        raise ValueError("Choose one or more unique configured noise levels")

    fraction = cfg.val_fraction if val_fraction is None else val_fraction
    if post_hoc is None and fraction != cfg.val_fraction:
        post_hoc = "p2"
    extra = {}
    if post_hoc is not None:
        if post_hoc not in ANALYSES or smoke:
            raise ValueError("Choose post-hoc analysis p1 or p2 without --smoke")
        scenario_fraction, folder = ANALYSES[post_hoc]
        fraction = scenario_fraction if val_fraction is None else val_fraction
        if fraction != scenario_fraction:
            raise ValueError(f"{post_hoc} requires --val-fraction {scenario_fraction:.2f}")
        destination = post_hoc_destination(cfg, out_dir or results_dir(cfg, "rq1_posthoc") / folder)
        extra = {
            "analysis": POST_HOC_TITLE,
            "scenario": post_hoc,
            "val_fraction": fraction,
            "blocking_fields": list(blocking_fields(cfg)),
        }
    else:
        destination = _destination(cfg, out_dir, smoke)
    protect_frozen_results(cfg, destination)
    grid = _thresholds(cfg.tau_grid)
    base = load_noisy(chosen_seeds[0], 0.0, cfg)
    sample = _sample_for_smoke(base, cfg) if smoke else None
    eid = cfg.columns.entity_id
    tuning = RunRecorder((*TAU_COLUMNS, "method") if post_hoc else TAU_COLUMNS)
    new_splits = {}
    results = RunRecorder(RAW_COLUMNS)
    for seed in chosen_seeds:
        if fraction == cfg.val_fraction:
            split = load_split(splits_dir(cfg) / f"split_seed{seed}.json")
        else:
            split = split_entities(base[eid], fraction, make_rng(seed, "split"))
            new_splits[seed] = split
        validation, tests = {}, {}
        for level in levels:
            frame = base if level == 0 else align_noisy_records(base, load_noisy(seed, level, cfg), cfg)
            val, test = apply_split(frame, split, cfg)
            if sample is not None:
                val, test = val.loc[val[eid].isin(sample)], test.loc[test[eid].isin(sample)]
            if val.empty or test.empty:
                raise ValueError(f"Seed {seed} requires non-empty validation and test splits")
            validation[level], tests[level] = val, test

        policies = {}
        tuning_method = {"method": "bloom_fuzzy"} if post_hoc else {}
        for field_set in cfg.field_sets:
            table = tune_tau(validation, grid, {"cfg": cfg, "field_set": field_set})
            for row in table.to_dict("records"):
                tuning.add({"seed": seed, "field_set": field_set, **row, **tuning_method})
            policies[field_set] = select_single_tau(table), select_per_noise_tau(table)

        if post_hoc:
            table = tune_blocked_tau(validation, grid, cfg)
            for row in table.to_dict("records"):
                tuning.add({"seed": seed, "field_set": DESCRIPTION, "method": BLOOM_BLOCKED, **row})
            blocked_tau = select_single_tau(table)
            blocked = BloomBlockedLinker(blocked_tau, cfg)

        for axes in iter_grid({"noise_level": list(levels), "field_set": list(cfg.field_sets)}):
            level, field_set = axes["noise_level"], axes["field_set"]
            single, per_noise = policies[field_set]
            _evaluate_test(tests[level], cfg, field_set, seed, level, single, per_noise[level], results)
        if post_hoc:
            for level in levels:
                _record_test(tests[level], cfg, DESCRIPTION, seed, level, ((blocked, "single", blocked_tau),), results)

    destination.mkdir(parents=True, exist_ok=True)
    if new_splits:
        split_dir = post_hoc_destination(cfg, destination / "splits")
        split_dir.mkdir(exist_ok=True)
        for seed, split in new_splits.items():
            save_split(split, split_dir / f"split_seed{seed}.json")
    with TemporaryDirectory(dir=destination) as staging:
        stage = Path(staging)
        write_csv(results.to_frame(), stage / "raw_runs.csv")
        write_csv(tuning.to_frame(), stage / "tau_selection.csv")
        write_metadata(
            stage / "metadata.json",
            replace(cfg, val_fraction=fraction) if post_hoc else cfg,
            chosen_seeds,
            extra={
                "noise_levels": list(levels),
                "smoke": smoke,
                "n_dataset_entities": base[eid].nunique() if sample is None else len(sample),
                **extra,
            },
        )
        for filename in ("raw_runs.csv", "tau_selection.csv", "metadata.json"):
            (stage / filename).replace(destination / filename)
    return destination


def _parse_noise_level(value: str) -> float:
    number = float(value.rstrip("%"))
    return number / 100 if value.endswith("%") or number > 1 else number


def main(argv: Sequence[str] | None = None) -> None:
    """Run the RQ1 experiment from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs="+", type=int, help="configured split seeds")
    parser.add_argument(
        "--noise-levels", nargs="+", type=_parse_noise_level, help="levels such as 0.05, 5, or 5%"
    )
    parser.add_argument("--out-dir", type=Path, help="override the output directory for a regular run")
    parser.add_argument("--post-hoc", choices=ANALYSES, help="run the labeled post-hoc analysis P1 or P2")
    parser.add_argument("--val-fraction", type=float, help="validation entity share, 0.30 for P1 or 0.50 for P2")
    parser.add_argument("--smoke", action="store_true", help="run seed 0 and write to results/rq1/smoke")
    args = parser.parse_args(argv)
    try:
        destination = run_experiment(
            load_config("rq1"),
            seeds=args.seeds,
            noise_levels=args.noise_levels,
            out_dir=args.out_dir,
            smoke=args.smoke,
            post_hoc=args.post_hoc,
            val_fraction=args.val_fraction,
        )
    except ValueError as exc:
        parser.error(str(exc))
    label = POST_HOC_TITLE if args.post_hoc or args.val_fraction == 0.50 else "RQ1 results"
    print(f"{label} written to {destination}")


if __name__ == "__main__":
    main()
