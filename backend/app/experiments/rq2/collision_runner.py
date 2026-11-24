"""Run the empirical RQ2 collision benchmark, its replay gate or its pilot."""

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pandas as pd

from src.common.config import all_fields_noise, load_config
from src.common.data.loader import load_noisy, noisy_csv_path
from src.common.paths import results_dir
from src.rq2.collision_cohorts import (
    build_seed_partition, derive_experiment_keys, encoder_for_cell, load_collision_cohorts, load_experiment_root,
)
from src.rq2.collision_config import CollisionConfig, load_collision_config
from src.rq2.collision_gate import collision_regression_gate, frozen_hashes
from src.rq2.collision_runs import (
    CollisionRuns, attack_control_passed, evaluate_bloom_cell, evaluate_exact_baseline, measure_control,
)
from src.rq2.collision_schema import write_collision_csv
from src.rq2.collision_selection import select_collision_config


def _write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _pilot_result(cfg, results, split, fingerprint):
    selection = select_collision_config(pd.DataFrame(results.validation), cfg)
    table = selection.table
    baseline = table.loc[(table["l"] == cfg.baseline[0]) & (table["k"] == cfg.baseline[1])].iloc[0]
    winner = table.loc[table["recommended"]].iloc[0]
    baseline_attack = float(baseline["validation_attack_success"])
    reduction = (baseline_attack - float(winner["validation_attack_success"])) / baseline_attack if baseline_attack else 0.0
    step = Decimal(str(cfg.pilot.reduction_step))
    proposed = float(max(step, (Decimal(str(reduction)) // step) * step))
    return {
        "seed": cfg.pilot.seed, "key_fingerprint": fingerprint,
        "validation_entities": len(split["validation"]), "reference_entities": len(split["reference"]),
        "baseline": list(cfg.baseline), "best_pilot_cell": list(selection.recommended),
        "baseline_validation_f1": float(baseline["validation_f1"]), "pilot_best_validation_f1": float(winner["validation_f1"]),
        "baseline_validation_attack_success": baseline_attack,
        "pilot_best_validation_attack_success": float(winner["validation_attack_success"]),
        "observed_relative_reduction": reduction, "proposed_h3_relative_reduction": proposed,
        "f1_budget": cfg.analysis.f1_budget,
    }


def _run_cells(
    results, cohorts, rq1, cfg, pairs, seed, noise, variant, key, historical, *, histograms=False
):
    for pair in pairs:
        evaluate_bloom_cell(
            results, cohorts, rq1, cfg, seed=seed, noise=noise, variant=variant, pair=pair, key=key,
            historical_tau=historical[seed] if pair == cfg.baseline and "test" in cohorts else None,
            collect_histograms=histograms,
        )


def run_collision_benchmark(
    cfg: CollisionConfig, *, stage: str, destination: Path, extended: bool = False, all_fields: bool = False,
) -> Path:
    rq1 = load_config("rq1")
    frozen = results_dir(rq1, "rq1")
    destination = destination.resolve()
    if destination.is_relative_to(frozen) or frozen.is_relative_to(destination):
        raise ValueError("RQ2 output must be separate from the frozen RQ1 directory")
    if stage == "main" and cfg.analysis.h3_relative_reduction is None:
        raise ValueError("Run the pilot and freeze the H3 reduction threshold before the main grid")

    gate, historical, hashes = collision_regression_gate(
        rq1, frozen, cfg.gate_seeds, cfg.primary_noise, cfg.field_set, cfg.baseline,
    )
    destination.mkdir(parents=True, exist_ok=True)
    write_collision_csv("regression_gate", gate, destination)
    _write_json(destination / "regression_hashes.json", hashes)
    print(f"Regression gate passed for {len(gate)} seeds with {len(hashes)} unchanged artifacts.", flush=True)
    for row in gate.itertuples(index=False):
        print(f"  seed {row.seed}: mean Q {row.q_mean:.5f}, median Q {row.q_median:g}, |U| {row.universe_size}", flush=True)
    if stage == "gate":
        return destination

    root = load_experiment_root(cfg, rq1)
    base = load_noisy(cfg.seeds[0], 0, rq1)
    partitions = {seed: build_seed_partition(base, rq1, cfg, seed) for seed in cfg.seeds}
    fingerprints = {}
    control_rows = []
    primary_cohorts = {}
    all_fields_config = all_fields_noise(rq1) if all_fields else None
    if all_fields_config is not None:
        missing = [seed for seed in cfg.seeds if not noisy_csv_path(seed, cfg.all_fields_noise, all_fields_config).is_file()]
        if missing:
            raise ValueError(f"Pre-generated all-fields artifacts are missing for seeds {missing}")
    for seed, split in partitions.items():
        key, _ = derive_experiment_keys(root, seed)
        fingerprints[seed] = hashlib.sha256(key).hexdigest()[:12]
        encoder = encoder_for_cell(rq1, cfg.controls.positive, key)
        primary_cohorts[seed] = load_collision_cohorts(base, rq1, cfg, seed, cfg.primary_noise, split, encoder)
        control_rows.extend(measure_control(primary_cohorts[seed], encoder, cfg, seed))
    controls = pd.DataFrame(control_rows)
    write_collision_csv("controls", controls, destination)
    if not attack_control_passed(controls, cfg):
        raise ValueError(f"Frequency controls failed. Inspect {destination / 'controls.csv'}. Grid withheld.")
    for name, rows in controls.groupby("split"):
        success, baseline = rows[["attack_success", "random_baseline"]].mean()
        print(f"Control {name}: success={success:.6f}, random={baseline:.6f}, lift={success / baseline:.2f}x, "
              f"max random gap={rows['random_gap'].max():.6f}", flush=True)
    if stage == "controls":
        return destination

    results = CollisionRuns()
    pairs = cfg.extended_grid if extended else cfg.primary_grid
    if stage == "pilot":
        seed = cfg.pilot.seed
        key, _ = derive_experiment_keys(root, seed)
        split = build_seed_partition(base, rq1, cfg, seed, pilot=True)
        encoder = encoder_for_cell(rq1, cfg.baseline, key)
        cohorts = load_collision_cohorts(base, rq1, cfg, seed, cfg.primary_noise, split, encoder, include_test=False)
        _run_cells(results, cohorts, rq1, cfg, cfg.primary_grid, seed, cfg.primary_noise, "description", key, historical)
        pilot = _pilot_result(cfg, results, split, fingerprints[seed])
        _write_json(destination / "pilot.json", pilot)
        print(json.dumps(pilot, indent=2), flush=True)
        return destination

    for seed, cohorts in primary_cohorts.items():
        key, exact = derive_experiment_keys(root, seed)
        _run_cells(results, cohorts, rq1, cfg, pairs, seed, cfg.primary_noise, "description", key, historical,
                   histograms=True)
        evaluate_exact_baseline(results, cohorts["test"], rq1, cfg, seed=seed, key=exact)
        print(f"Primary grid complete for seed {seed}.", flush=True)
    selection = select_collision_config(pd.DataFrame(results.validation), cfg)
    robustness_pairs = tuple(dict.fromkeys((cfg.baseline, selection.recommended, selection.extreme)))
    print(f"Validation selected {selection.recommended}. Robustness cells are {robustness_pairs}.", flush=True)
    robustness = [(rq1, "description", noise) for noise in cfg.robustness_noise]
    if all_fields_config is not None:
        robustness.append((all_fields_config, "all_fields", cfg.all_fields_noise))
    for noise_cfg, variant, noise in robustness:
        for seed, split in partitions.items():
            key, _ = derive_experiment_keys(root, seed)
            encoder = encoder_for_cell(rq1, cfg.baseline, key)
            cohorts = load_collision_cohorts(base, noise_cfg, cfg, seed, noise, split, encoder)
            _run_cells(results, cohorts, noise_cfg, cfg, robustness_pairs, seed, noise, variant, key, historical)
        print(f"Robustness complete for {variant} noise {noise:g}.", flush=True)

    if frozen_hashes(frozen) != hashes:
        raise ValueError("Frozen RQ1 artifacts changed after the gate")
    from src.rq2.collision_reporting import write_collision_report

    write_collision_report(results, selection, gate, controls, cfg, destination, fingerprints, partitions, extended)
    return destination


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("gate", "controls", "pilot", "main"), default="main")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--extended", action="store_true")
    parser.add_argument("--all-fields", action="store_true")
    args = parser.parse_args(argv)
    if args.stage != "main" and (args.extended or args.all_fields):
        parser.error("--extended and --all-fields are main-run options")
    try:
        cfg = load_collision_config(args.config)
        directory = results_dir(load_config("rq1"), "rq2")
        destination = args.out or (directory / args.stage if args.stage != "main"
                                   else directory / "extended" if args.extended else directory)
        print(f"RQ2 collision artifacts written to {run_collision_benchmark(cfg, stage=args.stage, destination=destination, extended=args.extended, all_fields=args.all_fields)}")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
