"""Validation tuning and output locations for the two post-hoc RQ1 analyses."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from src.common.config import Config
from src.common.evaluation.metrics import evaluate_clusters
from src.common.linking.bloom_blocked import BloomBlockedLinker
from src.common.paths import results_dir

ANALYSES = {"p1": (0.30, "p1_blocked_split3070"), "p2": (0.50, "p2_split5050")}
POST_HOC_TITLE = "Post-hoc analysis"


def protect_frozen_results(cfg: Config, path: Path) -> None:
    """Reject writes into an existing final RQ1 report tree."""
    frozen = results_dir(cfg, "rq1")
    final_files = ("raw_runs.csv", "tau_selection.csv", "metadata.json", "h1_check.md")
    if path.resolve().is_relative_to(frozen) and all((frozen / name).is_file() for name in final_files):
        raise ValueError("The final results/rq1 directory is frozen. Choose a separate output directory.")


def post_hoc_destination(cfg: Config, path: Path) -> Path:
    """Resolve a post-hoc destination inside the dedicated results tree."""
    frozen = results_dir(cfg, "rq1").resolve()
    root = results_dir(cfg, "rq1_posthoc").resolve()
    path = path.resolve()
    if path.is_relative_to(frozen) or not path.is_relative_to(root) or path == root:
        raise ValueError("Post-hoc outputs must be in a subdirectory of results/rq1_posthoc")
    return path


def tune_blocked_tau(
    validation: Mapping[float, pd.DataFrame], grid: Sequence[float], cfg: Config
) -> pd.DataFrame:
    """Sweep the configured grid over validation frames for selection by select_single_tau."""
    rid, eid = cfg.columns.record_id, cfg.columns.entity_id
    tau_min = min(grid)
    linker = BloomBlockedLinker(tau_min, cfg)
    rows = []
    for level, frame in validation.items():
        truth = frame.set_index(rid)[eid]
        prepared = linker.prepare(frame.drop(columns=eid), tau_min)
        for tau in grid:
            scores = evaluate_clusters(truth, prepared.labels_at(tau))
            rows.append((level, tau, scores["precision"], scores["recall"], scores["f1"]))
    return pd.DataFrame(rows, columns=("noise_level", "tau", "precision", "recall", "f1"))
