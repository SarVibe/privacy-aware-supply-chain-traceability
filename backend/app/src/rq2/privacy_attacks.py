"""Attacks used to *measure* empirical privacy.

A1  reid_attack        dictionary re-identification, key leaked (worst case).
                       Attacker encodes its public dictionary with the same
                       (key, l, k, q) and ranks it by Dice against each stored filter.
                       Success is the *expected* top-k hit rate with uniformly random
                       tie-breaking, so collisions (ties / near-ties) directly lower it.
A2  frequency_attack   frequency alignment, key secret. Distinct stored tokens are ranked
                       by count and aligned with the dictionary ranked by public frequency.
                       Works on any token (Bloom filter bytes or exact hashes).
A3  bit_qgram_attack   simplified bit-frequency / q-gram-frequency attack, key secret.
                       For each of the most frequent bit positions the attacker guesses the
                       q-gram whose public document-frequency is closest to the bit's
                       frequency. Success = the guessed q-gram really hashes to that bit.
                       (A simplified frequency attack, not a re-implementation of the
                       published cryptanalysis attacks.)
"""
from collections import Counter

import numpy as np

from .experiment_config import RQ2_CONFIG
from src.common.similarity.dice import dice_matrix

TIE_EPS = 1e-9


def reid_attack(
    victim_bf, victim_truth, dict_bf, dict_ids, topk=RQ2_CONFIG.sweep.reid_topk, delta=RQ2_CONFIG.sweep.reid_delta
) -> dict:
    n = victim_bf.shape[0]
    D = dice_matrix(victim_bf, dict_bf)                       # (n, m)
    pos_of = {int(e): j for j, e in enumerate(dict_ids)}
    j_true = np.array([pos_of.get(int(t), -1) for t in victim_truth])
    in_dict = j_true >= 0
    best = D.max(axis=1)
    denominator = max(1, dict_bf.shape[0])
    reid_ties_count = float((D >= best[:, None] - TIE_EPS).sum(1).mean())
    reid_cands_delta_count = float((D >= best[:, None] - delta).sum(1).mean())
    out = {
        "reid_ties_frac": reid_ties_count / denominator,
        "reid_cands_delta_frac": reid_cands_delta_count / denominator,
        # integer (rounded) mean counts — the primary reported columns
        "reid_ties_count": int(round(reid_ties_count)),
        "reid_cands_delta_count": int(round(reid_cands_delta_count)),
        "reid_ties": int(round(reid_ties_count)),
        "reid_cands_delta": int(round(reid_cands_delta_count)),
        "dict_coverage": float(in_dict.mean()),
    }
    s_true = np.where(in_dict, D[np.arange(n), np.maximum(j_true, 0)], np.nan)
    greater = (D > s_true[:, None] + TIE_EPS).sum(1)
    ties = np.maximum((np.abs(D - s_true[:, None]) <= TIE_EPS).sum(1), 1)
    anonymity_sets = np.where(
        in_dict,
        (D >= s_true[:, None] - TIE_EPS).sum(1),
        np.nan,
    )
    ranks = np.where(
        in_dict,
        1.0 + greater + 0.5 * np.maximum(ties - 1, 0),
        np.nan,
    )
    out["anonymity_set"] = float(np.nanmedian(anonymity_sets)) if in_dict.any() else float("nan")
    out["anonymity_set_mean"] = float(np.nanmean(anonymity_sets)) if in_dict.any() else float("nan")
    out["mean_rank"] = float(np.nanmean(ranks)) if in_dict.any() else float("nan")
    out["mrr"] = float(np.nanmean(1.0 / ranks)) if in_dict.any() else float("nan")
    for k in topk:
        p = np.clip((k - greater) / ties, 0.0, 1.0)
        out[f"reid_top{k}"] = float(np.where(in_dict, p, 0.0).mean())
    return out


def exact_reid_attack(victim_tokens, victim_truth, dict_tokens, dict_ids, topk=RQ2_CONFIG.sweep.reid_topk) -> dict:
    """Same attack against exact hashes: a victim is re-identified iff its token equals a dictionary token."""
    by_tok = {}
    for t, e in zip(dict_tokens, dict_ids):
        by_tok.setdefault(t, []).append(int(e))
    hit = {k: 0.0 for k in topk}
    top1_hits = 0.0
    cand_sizes = []
    for t, truth in zip(victim_tokens, victim_truth):
        c = by_tok.get(t)
        if not c:
            continue
        cand_sizes.append(len(c))
        if int(truth) in c:
            top1_hits += 1.0 / len(c)
            for k in topk:
                hit[k] += min(1.0, k / len(c))
    n = len(victim_tokens)
    out = {f"reid_top{k}": hit[k] / n if n else float("nan") for k in topk}
    out["reid_top1_conditional"] = top1_hits / len(cand_sizes) if cand_sizes else float("nan")
    denominator = max(1, len(dict_tokens))
    # Rounded mean dictionary candidate count among victims with candidates.
    ties_count_mean = float(np.mean(cand_sizes)) if cand_sizes else float("nan")
    out["reid_ties"] = int(round(ties_count_mean)) if cand_sizes else float("nan")
    out["reid_ties_frac"] = ties_count_mean / denominator if cand_sizes else float("nan")
    out["reid_ties_count"] = out["reid_ties"]
    out["reid_cands_delta"] = out["reid_ties"]
    out["reid_cands_delta_frac"] = out["reid_ties_frac"]
    out["reid_cands_delta_count"] = out["reid_ties_count"]
    out["dict_coverage"] = float(np.mean([int(t) in set(dict_ids) for t in victim_truth])) if n else 0.0
    out["anonymity_set"] = ties_count_mean if cand_sizes else float("nan")
    out["anonymity_set_mean"] = ties_count_mean if cand_sizes else float("nan")
    out["mean_rank"] = 1.0 if cand_sizes else float("nan")
    out["mrr"] = 1.0 if cand_sizes else float("nan")
    return out


def frequency_attack(tokens, truth, aux_counts: dict, rng: np.random.Generator) -> float:
    """Record-weighted fraction of stored records whose token is mapped to the correct entity."""
    if not tokens:
        raise ValueError("tokens must not be empty")
    if not aux_counts:
        raise ValueError("aux_counts must not be empty")
    cnt = Counter(tokens)
    toks = list(cnt)
    rng.shuffle(toks)                        # random tie-break among equal counts
    toks.sort(key=lambda t: -cnt[t])         # stable sort keeps the random order inside ties
    ents = list(aux_counts)
    rng.shuffle(ents)
    ents.sort(key=lambda e: -aux_counts[e])
    guess = dict(zip(toks, ents))
    hits = sum(1 for t, e in zip(tokens, truth) if guess.get(t, -1) == int(e))
    return hits / len(tokens)


def bit_qgram_attack(bf_victim, encoder, aux_grams, aux_df, top_bits, rng: np.random.Generator):
    """Returns (success_rate, random_baseline, mean_qgrams_per_attacked_bit)."""
    G = len(aux_grams)
    if G == 0:
        return float("nan"), float("nan"), float("nan")
    f = bf_victim.mean(axis=0)
    pos = encoder.gram_positions(aux_grams)                   # (G, k)
    member = np.zeros((G, bf_victim.shape[1]), dtype=bool)
    member[np.arange(G)[:, None], pos] = True
    per_bit = member.sum(axis=0)
    top = np.argsort(-f, kind="stable")[:top_bits]
    df = np.asarray(aux_df, dtype=float) + rng.uniform(0, 1e-9, G)
    hits = sum(bool(member[int(np.argmin(np.abs(df - f[b]))), b]) for b in top)
    return hits / len(top), float(np.mean(per_bit[top] / G)), float(per_bit[top].mean())
