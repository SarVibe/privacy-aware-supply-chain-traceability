"""Fixed record-order subsets of the final RQ1 data and saved entity splits."""

from dataclasses import dataclass, replace

import pandas as pd

from src.common.config import Config, load_config
from src.common.data.loader import align_noisy_records, load_noisy
from src.common.data.splitting import apply_split, load_split
from src.common.paths import app_dir, splits_dir
from src.common.seeding import make_rng

OUTPUT_ROOT = app_dir().parents[1] / "outputs" / "diagnostics"
GOLDEN_ROOT = app_dir() / "tests" / "golden"


@dataclass(frozen=True)
class DiagnosticCase:
    dataset: str
    seed: int
    noise: float
    clean: pd.DataFrame
    observed: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame


def _fixed_entity_subset(frame, entity_column, limit, seed):
    counts = frame.groupby(entity_column, sort=True).size()
    selected, remaining = set(), limit
    for entity in make_rng(seed, "diagnostics:fixed_entity_subset").permutation(counts.index):
        size = int(counts[entity])
        if size <= remaining:
            selected.add(entity)
            remaining -= size
        if not remaining:
            break
    if remaining:
        raise ValueError(f"Whole entity groups could not fill the {limit}-record budget")
    return selected


def diagnostic_cases(cfg: Config | None = None):
    """Use the 200-row golden and the same 1,000 records across the first three configured seeds."""
    cfg = cfg if cfg is not None else load_config("rq1")
    golden = (GOLDEN_ROOT / "rq1").relative_to(app_dir())
    fixture = replace(cfg, paths=replace(
        cfg.paths, prepared=str(golden / "prepared"), noisy=str(golden / "noisy"), splits=str(golden / "splits"),
    ))
    eid = cfg.columns.entity_id
    for label, source, seeds, limit in (
        ("golden_200", fixture, cfg.seeds[:1], 200),
        ("fixed_1000", cfg, cfg.seeds[:3], 1000),
    ):
        baseline = load_noisy(seeds[0], 0, source)
        selected = set(baseline[eid]) if label == "golden_200" else _fixed_entity_subset(
            baseline, eid, limit, seeds[0]
        )
        clean = baseline.loc[baseline[eid].isin(selected)].reset_index(drop=True)
        if len(clean) != limit:
            raise ValueError(f"Expected {limit} records in {label}")
        for seed in seeds:
            partition = load_split(splits_dir(source) / f"split_seed{seed}.json")
            partition = {name: [entity for entity in ids if entity in selected] for name, ids in partition.items()}
            for noise in cfg.noise_levels:
                recorded = baseline if noise == 0 else load_noisy(seed, noise, source)
                observed = align_noisy_records(clean, recorded.loc[recorded[eid].isin(selected)], source)
                val, test = apply_split(observed, partition, source)
                yield DiagnosticCase(label, seed, noise, clean, observed, val, test)
