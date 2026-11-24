"""Sweep and select Bloom thresholds using validation frames."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import NotRequired, TypedDict

import pandas as pd

from src.common.config import Config, TauGridConfig
from src.common.evaluation.metrics import evaluate_clusters
from src.common.linking.bloom import BloomLinker


class BloomLinkerArgs(TypedDict):
    """Arguments shared by Bloom linkers during a validation sweep."""

    cfg: Config
    field_set: str
    name: NotRequired[str]


def threshold_values(grid: TauGridConfig) -> tuple[float, ...]:
    """Expand configured decimal endpoints without cumulative rounding error."""
    start, stop, step = (Decimal(str(value)) for value in (grid.start, grid.stop, grid.step))
    if not (0 <= start <= stop <= 1 and step > 0):
        raise ValueError("tau_grid requires 0 <= start <= stop <= 1 and a positive step")
    return tuple(float(start + i * step) for i in range(int((stop - start) // step) + 1))


def tune_tau(
    val_frames_by_noise: Mapping[float, pd.DataFrame],
    tau_grid: Sequence[float],
    linker_factory_args: BloomLinkerArgs,
) -> pd.DataFrame:
    """Evaluate each cutoff on validation data, preparing similarities once per level."""
    grid = tuple(tau_grid)
    if not grid or any(not 0 <= tau <= 1 for tau in grid) or len(set(grid)) != len(grid):
        raise ValueError("tau_grid must contain unique thresholds in [0, 1]")
    if not val_frames_by_noise:
        raise ValueError("At least one validation frame is required")
    cfg = linker_factory_args["cfg"]
    rid, eid = cfg.columns.record_id, cfg.columns.entity_id
    tau_min = min(grid)
    linker = BloomLinker(
        linker_factory_args.get("name", "bloom_fuzzy"), linker_factory_args["field_set"], tau_min, cfg
    )
    rows = []
    for level, frame in val_frames_by_noise.items():
        truth = frame.set_index(rid)[eid]
        prepared = linker.prepare(frame.drop(columns=eid), tau_min)
        for tau in grid:
            metrics = evaluate_clusters(truth, prepared.labels_at(tau))
            rows.append((level, tau, metrics["precision"], metrics["recall"], metrics["f1"]))
    return pd.DataFrame(rows, columns=("noise_level", "tau", "precision", "recall", "f1"))


def select_single_tau(table: pd.DataFrame) -> float:
    """Maximize mean validation F1 across noise levels, with higher tau winning ties."""
    if table.empty:
        raise ValueError("Cannot select a threshold from an empty validation table")
    scores = table.groupby("tau")["f1"].mean()
    return float(max(scores.index, key=lambda tau: (scores[tau], tau)))


def select_per_noise_tau(table: pd.DataFrame) -> dict[float, float]:
    """Maximize validation F1 per noise level, with higher tau winning ties."""
    if table.empty:
        raise ValueError("Cannot select thresholds from an empty validation table")
    ranked = table.sort_values(["f1", "tau"], ascending=False)
    best = ranked.drop_duplicates(subset="noise_level")
    return {float(level): float(tau) for level, tau in zip(best["noise_level"], best["tau"])}
