"""Validation-only cutoff selection and held-out pair/cluster diagnostics."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from src.common.config import Config
from src.common.evaluation.metrics import evaluate_clusters, pairwise_prf
from src.common.linking.bloom import PreparedBloom
from src.common.linking.exact import ExactLinker, NORMALIZED_EXACT
from src.common.linking.threshold import select_single_tau
from src.rq2.collision_cohorts import Cohort
from src.rq2.collision_linkage import score_collision_clusters


@dataclass(frozen=True)
class Separation:
    pr_auc: float
    dice_overlap: float
    match: np.ndarray
    nonmatch: np.ndarray


def validation_cutoff(
    cohort: Cohort, prepared: PreparedBloom, taus: tuple[float, ...], cfg: Config
) -> tuple[float, pd.DataFrame]:
    sweep = pd.DataFrame({"tau": tau, **score_collision_clusters(cohort.frame, prepared, tau, cfg)} for tau in taus)
    return select_single_tau(sweep), sweep


def _pair_status(truth: pd.Series, i: np.ndarray, j: np.ndarray) -> np.ndarray:
    values = truth.to_numpy()
    return values[i] == values[j]


def _score_pairs(truth, labels, parties, i, j, scores, bins):
    matches = _pair_status(truth, i, j)
    cross = parties[i] != parties[j]
    predicted = _pair_status(labels, i[cross], j[cross])
    eligible_truth = matches[cross]
    cross_prf = pairwise_prf(
        int((predicted & eligible_truth).sum()), int(predicted.sum()), int(eligible_truth.sum())
    )
    hist = []
    for values in (scores[matches], scores[~matches]):
        counts = np.histogram(values, bins=bins, range=(0, 1))[0]
        hist.append(counts)
    match, nonmatch = hist
    both_classes = bool(match.sum() and nonmatch.sum())
    overlap = float(np.minimum(match / match.sum(), nonmatch / nonmatch.sum()).sum()) if both_classes else float("nan")
    ap = float(average_precision_score(matches, scores)) if both_classes else float("nan")
    return dict(zip(("cross_party_precision", "cross_party_recall", "cross_party_f1"), cross_prf)), Separation(
        ap, overlap, match, nonmatch
    )


def score_bloom_test(
    cohort: Cohort, prepared: PreparedBloom, cfg: Config, tau: float, bins: int,
    historical_tau: float | None,
) -> tuple[dict, Separation]:
    truth = cohort.frame.set_index(cfg.columns.record_id)[cfg.columns.entity_id]
    labels = prepared.labels_at(tau)
    cross, separation = _score_pairs(truth, labels, cohort.parties, prepared.i, prepared.j, prepared.sim, bins)
    historical = {}
    if historical_tau is not None:
        historical = score_collision_clusters(cohort.frame, prepared, historical_tau, cfg)
    return {
        **evaluate_clusters(truth, labels), **cross,
        "historical_tau": historical_tau,
        **{f"historical_{name}": historical.get(name) for name in ("precision", "recall", "f1")},
    }, separation


def score_exact_test(
    cohort: Cohort, cfg: Config, field_set: str, key: bytes, bins: int
) -> tuple[dict, Separation]:
    eid = cfg.columns.entity_id
    truth = cohort.frame.set_index(cfg.columns.record_id)[eid]
    labels = ExactLinker(NORMALIZED_EXACT, field_set, True, cfg, key=key).link(cohort.frame.drop(columns=eid))
    i, j = np.triu_indices(len(labels), k=1)
    scores = _pair_status(labels, i, j).astype(float)
    cross, separation = _score_pairs(truth, labels, cohort.parties, i, j, scores, bins)
    return {**evaluate_clusters(truth, labels), **cross}, separation
