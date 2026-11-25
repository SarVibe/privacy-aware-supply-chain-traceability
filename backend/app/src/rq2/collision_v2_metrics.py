"""Compute aggregate v2 endpoint measurements on approved research cohorts."""

from math import log

import numpy as np

from src.common.evaluation.metrics import count_same_label_pairs, pairwise_prf
from src.common.seeding import make_rng
from src.rq2.collision_privacy import FrequencyEvaluation

E1 = ("hit", "null_full", "null_matched", "excess_matched", "lift_matched", "excess_full", "lift_full", "used_bits")
E2 = ("e2_precision_mean", "e2_precision_median", "e2_false_candidates", "e2_exact_recovery")
STRUCTURE = ("fill", "fill_finite", "fill_exponential", "entropy", "q_mean", "q_median", "universe_size",
             "ambiguity_mean", "ambiguity_median", "f", "u_times_f", "k_opt", "false_candidates_finite")
EDGE = ("direct_precision", "direct_recall", "direct_f1", "true_pairs", "direct_tp", "direct_predicted",
        "direct_false", "cluster_tp", "cluster_predicted", "cluster_false", "closure_added_tp",
        "closure_added_false")


def matched_frequency(evaluator: FrequencyEvaluation, reference, seed: int, purpose: str) -> dict:
    """Use the original aligner and evaluate its same-pool uniform null."""
    legacy = evaluator.alignment_metrics(reference, seed, purpose)
    hit, full = legacy["attack_success"], legacy["random_baseline"]
    rows = np.flatnonzero([token in reference for token in evaluator.universe])
    matched = float(evaluator.membership[np.ix_(rows, evaluator.used)].mean())
    return {"hit": hit, "null_full": full, "null_matched": matched, "excess_matched": hit - matched,
            "lift_matched": hit / matched if matched else None, "excess_full": hit - full,
            "lift_full": hit / full, "used_bits": legacy["used_bits"]}


def matched_control(evaluator, reference, seed, split, settings) -> dict:
    result = matched_frequency(evaluator, reference, seed, f"rq2:control-positive:{split}")
    pool = np.flatnonzero([token in reference for token in evaluator.universe])
    rng = make_rng(seed, f"rq2:v2:control-negative:{split}")
    guesses = rng.choice(pool, size=(settings.random_trials, len(evaluator.used)))
    random_hit = float(evaluator.membership[guesses, evaluator.used].mean())
    gap = abs(random_hit - result["null_matched"])
    return {"seed": seed, "split": split, "l": settings.positive[0], "k": settings.positive[1], **result,
            "random_hit": random_hit, "random_gap": gap, "random_trials": settings.random_trials}


def known_key_metrics(bits, inserted: list[set[str]], evaluator: FrequencyEvaluation) -> dict:
    membership = evaluator.membership
    required = membership.sum(axis=1)
    candidates = (bits.astype(np.float32) @ membership.T.astype(np.float32)) == required
    token_index = {token: i for i, token in enumerate(evaluator.universe)}
    for row, tokens in enumerate(inserted):
        if not candidates[row, [token_index[token] for token in tokens]].all():
            raise AssertionError("Known-key membership failed to include an inserted token")
    true_count = np.array([len(tokens) for tokens in inserted])
    candidate_count = candidates.sum(axis=1)
    false_count = candidate_count - true_count
    precision = np.divide(true_count, candidate_count, out=np.ones(len(bits)), where=candidate_count > 0)
    return {"e2_precision_mean": float(precision.mean()), "e2_precision_median": float(np.median(precision)),
            "e2_false_candidates": float(false_count.mean()), "e2_exact_recovery": float((false_count == 0).mean())}


def finite_candidate_probability(counts: np.ndarray, length: int, hashes: int) -> np.ndarray:
    """Ideal probability of accepting an absent token, conditional on record token counts."""
    occupied = np.arange(length + 1, dtype=float) / length
    stay = occupied
    gain = 1 - occupied[:-1]
    query_membership = occupied ** hashes
    placements = counts * hashes
    wanted = set(placements.tolist())
    probabilities = {}
    distribution = np.zeros(length + 1)
    distribution[0] = 1
    last = int(placements.max())
    for step in range(last + 1):
        if step in wanted:
            probabilities[step] = float(distribution @ query_membership)
        if step < last:
            entered = distribution[:-1] * gain
            distribution *= stay
            distribution[1:] += entered
    return np.array([probabilities[step] for step in placements])


def v2_occupancy(bits, inserted, evaluator, hashes):
    length = bits.shape[1]
    counts = np.fromiter(map(len, inserted), dtype=int)
    summary = evaluator.structural_metrics(bits, inserted, hashes)
    finite = 1 - (1 - 1 / length) ** (hashes * counts)
    finite_candidates = (summary["universe_size"] - counts) * finite_candidate_probability(counts, length, hashes)
    return {name: summary[name] for name in ("fill", "entropy", "q_mean", "q_median", "universe_size",
                                             "ambiguity_mean", "ambiguity_median")} | {
        "fill_finite": float(finite.mean()), "fill_exponential": summary["fill_expected"],
        "f": summary["collision_proxy"], "u_times_f": summary["false_candidate_proxy"],
        "k_opt": length * log(2) / summary["q_mean"], "false_candidates_finite": float(finite_candidates.mean()),
    }


def diagnose_edges(prepared, truth, tau: float) -> dict:
    aligned = truth.reindex(prepared.record_ids)
    if aligned.isna().any() or not truth.index.is_unique or len(truth) != len(aligned):
        raise ValueError("Direct-edge diagnostics require unique aligned truth")
    keep = prepared.sim >= tau
    ids = aligned.to_numpy()
    direct_predicted = int(keep.sum())
    true_pairs = count_same_label_pairs(aligned)
    direct_tp = int((ids[prepared.i[keep]] == ids[prepared.j[keep]]).sum())
    labels = prepared.labels_at(tau)
    cluster_predicted = count_same_label_pairs(labels)
    cluster_tp = sum(count_same_label_pairs(group) for _, group in aligned.groupby(labels, sort=False))
    direct_false = direct_predicted - direct_tp
    cluster_false = cluster_predicted - cluster_tp
    precision, recall, score = pairwise_prf(direct_tp, direct_predicted, true_pairs)
    return {"direct_precision": precision, "direct_recall": recall, "direct_f1": score, "true_pairs": true_pairs,
            "direct_tp": direct_tp, "direct_predicted": direct_predicted, "direct_false": direct_false,
            "cluster_tp": cluster_tp, "cluster_predicted": cluster_predicted, "cluster_false": cluster_false,
            "closure_added_tp": cluster_tp - direct_tp, "closure_added_false": cluster_false - direct_false}
