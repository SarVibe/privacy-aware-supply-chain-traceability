"""Run the frozen RQ2 v2 correctness pilot or final benchmark."""

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter

import pandas as pd
from dotenv import load_dotenv

from src.common.config import all_fields_noise, load_config
from src.common.data.loader import load_noisy, noisy_csv_path
from src.common.data.schema import validate_frame
from src.common.experiment.io import write_csv
from src.common.noise.typo_noise import inject_noise
from src.common.paths import app_dir, results_dir
from src.common.seeding import make_rng
from src.rq2.collision_cohorts import build_seed_partition, encoder_for_cell, load_collision_cohorts
from src.rq2.collision_v2_analysis import select_v2_validation
from src.rq2.collision_v2_artifacts import export_v2_csv, verify_v1_freeze
from src.rq2.collision_v2_config import PROFILE, load_v2_protocol, research_root, v2_keys
from src.rq2.collision_v2_runs import V2Runs, control_v2_cohorts, entity_overlap, evaluate_v2_cell, v2_control_passed, v2_exact_row


def _protocol_commit(root: Path) -> str:
    paths = [PROFILE.relative_to(root).as_posix(), "docs/RQ2_V2_PROTOCOL.md"]
    status = subprocess.check_output(["git", "status", "--porcelain", "--", *paths], cwd=root, text=True)
    if status:
        raise ValueError("The V2 config and protocol must match the committed freeze")
    commit = subprocess.check_output(["git", "log", "-1", "--format=%H", "--", *paths], cwd=root, text=True).strip()
    if not commit:
        raise ValueError("Commit the V2 protocol and profile before evaluation")
    return commit


def _prepare_variant(base, rq1, destination, seed, level):
    cfg = replace(rq1, paths=replace(rq1.paths, noisy=destination.relative_to(app_dir()).as_posix()))
    noise, _ = inject_noise(base, level, cfg.noise_fields, cfg.typos_per_selected_record,
                            make_rng(seed, f"noise_{level}"), record_id_column=cfg.columns.record_id,
                            entity_id_column=cfg.columns.entity_id)
    validate_frame(noise, cfg)
    write_csv(noise, noisy_csv_path(seed, level, cfg))
    return cfg


def _evaluate_cells(results, cohorts, rq1, cfg, pairs, seed, level, variant, key, histograms=False):
    for pair in pairs:
        evaluate_v2_cell(results, cohorts, rq1, cfg, seed=seed, noise=level, variant=variant,
                         pair=pair, key=key, histograms=histograms)


def _key_fingerprints(bloom, exact):
    return {"bloom": hashlib.sha256(bloom).hexdigest()[:12], "exact": hashlib.sha256(exact).hexdigest()[:12]}


def run_v2_benchmark(stage: str) -> Path:
    app = app_dir()
    workspace = app.parents[1]
    protocol_commit = _protocol_commit(workspace)
    frozen = verify_v1_freeze()
    rq1, cfg = load_config("rq1"), load_v2_protocol()
    load_dotenv(workspace / ".env", override=False)
    root = research_root(cfg, rq1.bloom.hmac_key)
    directory = results_dir(rq1, "rq2_v2")
    destination = directory / "pilot" if stage == "pilot" else directory
    if stage == "main":
        path = directory / "pilot/metadata.json"
        pilot_meta = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        if pilot_meta.get("protocol_commit") != protocol_commit:
            raise ValueError("Complete the correctness pilot on the committed protocol before running V2")
        if pilot_meta["key_fingerprints"].get(str(cfg.pilot.seed)) != _key_fingerprints(*v2_keys(root, cfg.pilot.seed)):
            raise ValueError("Use the same fixed research key for the pilot and the final benchmark")
    os.environ.setdefault("MPLCONFIGDIR", str(directory / ".mplconfig"))
    base = load_noisy(cfg.seeds[0], 0.0, rq1)
    partitions = {seed: build_seed_partition(base, rq1, cfg, seed) for seed in cfg.seeds}
    entity = rq1.columns.entity_id
    entity_ids = sorted(base[entity].unique())
    pilot_ids = make_rng(cfg.pilot.seed, "rq2:v2:pilot-subset").choice(
        entity_ids, size=min(len(entity_ids), cfg.pilot.max_entities), replace=False
    )
    pilot_base = base.loc[base[entity].isin(pilot_ids)]
    pilot = build_seed_partition(pilot_base, rq1, cfg, cfg.pilot.seed)
    overlaps = entity_overlap(partitions, cfg.pilot.seed, pilot)
    active = {cfg.pilot.seed: pilot} if stage == "pilot" else partitions
    noise_cfg = rq1
    if stage == "pilot":
        noise_cfg = _prepare_variant(base, rq1, directory / "inputs/pilot", cfg.pilot.seed, cfg.primary_noise)
    cohorts_by_seed, keys, fingerprints, controls = {}, {}, {}, []
    for seed, split in active.items():
        bloom, exact = v2_keys(root, seed)
        keys[seed] = bloom, exact
        fingerprints[seed] = _key_fingerprints(bloom, exact)
        encoder = encoder_for_cell(rq1, cfg.controls.positive, bloom)
        cohorts = load_collision_cohorts(base, noise_cfg, cfg, seed, cfg.primary_noise, split, encoder)
        cohorts_by_seed[seed] = cohorts
        controls.extend(control_v2_cohorts(cohorts, encoder, seed, cfg))
    del root
    controls = pd.DataFrame(controls)
    for name, rows in controls.groupby("split"):
        hit, null = rows[["hit", "null_matched"]].mean()
        lift = hit / null if null else float("nan")
        print(f"{stage} control {name}: hit={hit:.6f}, matched null={null:.6f}, lift={lift:.3f}, "
              f"max random gap={rows['random_gap'].max():.6f}", flush=True)
    if not v2_control_passed(controls, cfg.controls):
        failure = destination / "failed_control_diagnostics"
        export_v2_csv("controls", controls, failure)
        from src.rq2.collision_v2_report import DISCLOSURE

        (failure / "summary.md").write_text(
            f"# RQ2 v2 control gate\n\n{DISCLOSURE}.\n\nThe control gate failed before grid scoring.\n",
            encoding="utf-8",
        )
        raise ValueError(f"V2 controls failed. Diagnostics are in {failure}")

    results = V2Runs()
    started = perf_counter()
    for seed, cohorts in cohorts_by_seed.items():
        bloom, exact = keys[seed]
        _evaluate_cells(results, cohorts, rq1, cfg, cfg.grid, seed, cfg.primary_noise, "description", bloom,
                        histograms=stage == "main")
        results.exact_baseline.append(v2_exact_row(cohorts["test"], rq1, cfg, seed, exact))
        print(f"{stage} primary grid completed for seed {seed}.", flush=True)
    seconds = perf_counter() - started
    selection = None
    if stage == "main":
        selection = select_v2_validation(pd.DataFrame(results.validation), cfg)
        roles = tuple(dict.fromkeys((cfg.baseline, selection[0], selection[1])))
        print(f"Validation selected {selection[0]}. Robustness cells: {roles}.", flush=True)
        jobs = [("description", level, rq1) for level in cfg.robustness_noise]
        jobs.append(("all_fields", cfg.all_fields_noise, all_fields_noise(rq1)))
        for variant, level, feature_cfg in jobs:
            for seed, split in active.items():
                key = keys[seed][0]
                if variant == "all_fields":
                    feature_cfg = _prepare_variant(base, feature_cfg, directory / "inputs/all_fields", seed, level)
                encoder = encoder_for_cell(rq1, cfg.baseline, key)
                cohorts = load_collision_cohorts(base, feature_cfg, cfg, seed, level, split, encoder)
                _evaluate_cells(results, cohorts, rq1, cfg, roles, seed, level, variant, key)
            print(f"Robustness completed for {variant} noise {level:g}.", flush=True)

    metadata = {"protocol_commit": protocol_commit, "stage": stage, "config": asdict(cfg),
                "grid_seconds": seconds, "key_fingerprints": fingerprints, "frozen_artifact_count": len(frozen),
                "entity_counts": {seed: {name: len(ids) for name, ids in split.items()} for seed, split in active.items()}}
    from src.rq2.collision_v2_report import write_v2_run_artifacts

    write_v2_run_artifacts(results, controls, overlaps, destination, cfg, metadata, selection)
    if verify_v1_freeze() != frozen:
        raise ValueError("Frozen artifact manifest changed during the V2 run")
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("pilot", "main"), required=True)
    args = parser.parse_args(argv)
    try:
        print(f"RQ2 v2 artifacts: {run_v2_benchmark(args.stage)}", flush=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
