"""Replay the frozen RQ1 cohort through the RQ2 collision linkage path."""

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from statistics import mean, median

import pandas as pd

from src.common.config import Config
from src.common.data.loader import load_linkage_data
from src.common.experiment.io import read_csv, require_columns
from src.rq2.collision_linkage import (
    build_collision_encoder, cohort_tokens, prepare_collision_scores, score_collision_clusters,
)

FROZEN_FILES = ("raw_runs.csv", "tau_selection.csv", "metadata.json", "h1_check.md")
GATE_METRICS = ("precision", "recall", "f1", "fragmentation_rate", "n_records", "n_entities", "n_pred_clusters")


def frozen_hashes(root: Path) -> dict[str, str]:
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in FROZEN_FILES}


def collision_regression_gate(
    cfg: Config, root: Path, seeds: Sequence[int], noise: float, field_set: str, baseline: tuple[int, int]
) -> tuple[pd.DataFrame, dict[int, float], dict[str, str]]:
    """Require exact round-trip equality on the original split, key and cutoff."""
    hashes = frozen_hashes(root)
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    fingerprint = hashlib.sha256(bytes.fromhex(cfg.bloom.hmac_key)).hexdigest()[:12]
    if fingerprint != metadata["config"]["bloom"]["hmac_key_fingerprint"]:
        raise ValueError("RQ1 gate key fingerprint differs from the frozen run")
    if (cfg.bloom.l, cfg.bloom.k) != baseline:
        raise ValueError("RQ1 gate dimensions differ from the configured baseline")

    frozen = read_csv(root / "raw_runs.csv", round_trip=True)
    require_columns(frozen, ("seed", "noise_level", "method", "field_set", "tau", "tau_mode", "split", *GATE_METRICS),
                    table="Frozen RQ1 runs")
    selected = frozen.loc[
        (frozen["method"] == "bloom_fuzzy") & (frozen["field_set"] == field_set) & (frozen["tau_mode"] == "single")
        & (frozen["split"] == "test") & (frozen["noise_level"] == noise) & frozen["seed"].isin(seeds)
    ].sort_values("seed")
    if selected["seed"].duplicated().any() or set(selected["seed"]) != set(seeds):
        raise ValueError("RQ1 gate requires one frozen composite single-cutoff row per requested seed")

    encoder = build_collision_encoder(cfg)
    results = []
    try:
        for row in selected.itertuples(index=False):
            data = load_linkage_data(cfg, row.seed, noise, field_set)
            test_tokens = cohort_tokens(data.test, cfg, field_set, encoder)
            prepared = prepare_collision_scores(data.test, encoder.encode_gram_sets(test_tokens), cfg)
            actual = score_collision_clusters(data.test, prepared, row.tau, cfg)
            for metric in GATE_METRICS:
                if actual[metric] != getattr(row, metric):
                    raise ValueError(
                        f"RQ1 gate seed {row.seed}, tau {row.tau}: {metric} "
                        f"expected {getattr(row, metric)!r}, got {actual[metric]!r}"
                    )
            tokens = cohort_tokens(data.noisy, cfg, field_set, encoder)
            counts = [len(grams) for grams in tokens]
            results.append({"seed": row.seed, "noise": noise, "l": baseline[0], "k": baseline[1], "tau": row.tau,
                            **actual, "q_mean": mean(counts), "q_median": median(counts),
                            "universe_size": len(set().union(*tokens)), "passed": True})
    finally:
        if frozen_hashes(root) != hashes:
            raise ValueError("Frozen RQ1 artifacts changed during the regression gate")
    return pd.DataFrame(results), dict(zip(selected["seed"], selected["tau"], strict=True)), hashes
