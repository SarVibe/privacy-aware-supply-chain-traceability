"""Build the RQ1 control dataset, entity splits and noisy datasets."""

import argparse
from dataclasses import replace

from tabulate import tabulate

from src.common.config import Config, load_config
from src.common.data.loader import (
    BASE_DATASET_FILENAME,
    ENTITY_MAP_FILENAME,
    noisy_csv_path,
    read_prepared_csv,
    read_raw_csv,
)
from src.common.data.preparation import prepare_base_data
from src.common.data.splitting import apply_split, save_split, split_entities
from src.common.noise.typo_noise import inject_noise
from src.common.paths import prepared_dir, splits_dir
from src.common.seeding import make_rng


def _prepare_base(cfg: Config) -> None:
    result = prepare_base_data(read_raw_csv(cfg), cfg)
    destination = prepared_dir(cfg, create=True)
    result.records.to_csv(destination / BASE_DATASET_FILENAME, index=False)
    result.entity_map.to_csv(destination / ENTITY_MAP_FILENAME, index=False)
    print(
        f"Base: {len(result.records):,} rows, {len(result.entity_map):,} entities "
        f"from {result.input_rows:,} raw rows"
    )
    print(
        f"Rows removed: {result.input_rows - len(result.records):,} "
        f"({result.empty_rows_removed:,} empty description or empty row, "
        f"{result.cap_rows_removed:,} from {result.entities_capped:,} capped entities, "
        f"{result.sample_rows_removed:,} from entity sampling). "
        f"Exact duplicate rows before cap and sampling: {result.exact_duplicates:,}."
    )


def _prepare_splits(cfg: Config) -> None:
    frame = read_prepared_csv(cfg)
    entity_ids = frame[cfg.columns.entity_id]
    destination = splits_dir(cfg, create=True)
    print(f"Splitting {len(frame):,} rows from {entity_ids.nunique():,} entities.")
    for seed in cfg.seeds:
        split = split_entities(entity_ids, cfg.val_fraction, make_rng(seed, "split"))
        validation, test = apply_split(frame, split, cfg)
        save_split(split, destination / f"split_seed{seed}.json")
        print(
            f"Seed {seed}: validation {len(split['validation']):,} entities / {len(validation):,} rows, "
            f"test {len(split['test']):,} entities / {len(test):,} rows"
        )


def _prepare_noise(cfg: Config) -> None:
    base = read_prepared_csv(cfg)
    rows = []
    for seed in cfg.seeds:
        for level in cfg.noise_levels:
            if level == 0:
                continue
            noisy, log = inject_noise(
                base,
                level,
                cfg.noise_fields,
                cfg.typos_per_selected_record,
                make_rng(seed, f"noise_{level}"),
                record_id_column=cfg.columns.record_id,
                entity_id_column=cfg.columns.entity_id,
            )
            destination = noisy_csv_path(seed, level, cfg)
            destination.parent.mkdir(parents=True, exist_ok=True)
            noisy.to_csv(destination, index=False)
            log.to_csv(destination.with_name(f"{destination.stem}_log.csv"), index=False)

            selected = log["record_id"].nunique()
            changed = log.loc[log["n_typos"] > 0, "record_id"].nunique()
            actual_rate = changed / len(base) if len(base) else 0.0
            mean_typos = log["n_typos"].sum() / selected if selected else 0.0
            skipped = int(log["skipped_reason"].ne("").sum())
            rows.append((seed, f"{level:.0%}", selected, f"{actual_rate:.3%}", mean_typos, skipped))
    print(
        tabulate(
            rows,
            headers=("Seed", "Level", "Selected records", "Actual rate", "Mean typos per selected record", "Skipped fields"),
            floatfmt=".3f",
        )
    )


def main(argv=None) -> None:
    """Run one RQ1 preparation stage."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("base", "split", "noise"))
    parser.add_argument("--all-fields", action="store_true", help="write the separately versioned all-field artifacts")
    parser.add_argument("--seeds", nargs="+", type=int, help="subset of configured seeds for the noise stage")
    parser.add_argument("--noise-levels", nargs="+", type=int, metavar="PERCENT")
    args = parser.parse_args(argv)
    if (args.all_fields or args.seeds or args.noise_levels) and args.stage != "noise":
        parser.error("--all-fields, --seeds and --noise-levels apply to the noise stage")
    cfg = load_config("rq1_all_fields" if args.all_fields else "rq1")
    if args.seeds is not None:
        if not set(args.seeds) <= set(cfg.seeds) or len(set(args.seeds)) != len(args.seeds):
            parser.error("Choose unique configured preparation seeds")
        cfg = replace(cfg, seeds=tuple(args.seeds))
    if args.noise_levels is not None:
        levels = tuple(level / 100 for level in args.noise_levels)
        if not set(levels) <= set(cfg.noise_levels) or len(set(levels)) != len(levels):
            parser.error("Choose unique configured noise percentages")
        cfg = replace(cfg, noise_levels=levels)
    if args.stage == "base":
        _prepare_base(cfg)
    elif args.stage == "split":
        _prepare_splits(cfg)
    else:
        _prepare_noise(cfg)


if __name__ == "__main__":
    main()
