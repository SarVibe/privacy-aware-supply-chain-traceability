"""One experimental run = Scenario (data-side randomness) x configuration (l, k, eps).

Scenario (depends on seed, noise, overlap only -> identical across (l, k), so
configurations are compared on *paired* data):
  * B = representatives of pre-generated noisy records; A = clean representatives.
  * the same validation/test entity split used for record linkage.
  * the attacker's public dictionary (a fraction `overlap` of the entities).
  * M victim records sampled from observed entity variants, plus auxiliary
    entity counts and public q-gram frequencies.
"""
import math
from dataclasses import dataclass

import numpy as np

from src.common.config import validate_epsilon
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.encoding.randomized_response import flip_probability, randomized_response, response_transform
from src.common.experiment.linkage import evaluate_bloom_linkage, evaluate_test_clusters
from src.common.linking.exact import ExactLinker, keyed_sha256
from src.common.seeding import make_rng
from src.common.similarity.dice import dice_matrix

from . import privacy_attacks as attacks
from . import privacy_metrics as metrics
from . import similarity_matching as matching
from .experiment_config import DEFAULT_Q, RQ2_CONFIG
from .parameter_validation import validate_bit_top, validate_dataset, validate_n_records, validate_noise, validate_overlap


@dataclass
class Scenario:
    seed: int
    noise: float
    overlap: float
    key: bytes
    pad_char: str
    b_norm: list
    val_idx: np.ndarray
    test_idx: np.ndarray
    dict_ids: np.ndarray
    dict_norm: list
    dict_extra_ratio: float
    victim_ids: np.ndarray
    victim_norm: list
    aux_counts: dict
    aux_grams: list
    aux_df: np.ndarray


def build_scenario(
    ds, seed: int, noise: float, overlap: float = RQ2_CONFIG.sweep.overlap,
    n_records: int = RQ2_CONFIG.sweep.victim_draws, q: int = DEFAULT_Q,
    *, dict_extra_ratio: float = RQ2_CONFIG.sweep.dict_extra_ratio,
) -> Scenario:
    validate_dataset(ds)
    noise = validate_noise(noise)
    overlap = validate_overlap(overlap)
    n_records = validate_n_records(n_records)
    rng = make_rng(seed, f"rq2:scenario:{noise}:{overlap}")
    n = ds.n
    if ds.noisy_norm is None:
        raise ValueError("Load pre-generated noisy records before building an RQ2 scenario")
    if ds.noise_level is not None and (ds.noise_level != noise or ds.seed != seed):
        raise ValueError("Noisy records must match the scenario's seed and noise level")
    b_norm = list(ds.noisy_norm)
    if ds.linkage is not None:
        eid = ds.linkage.config.columns.entity_id
        test_entities = set(ds.linkage.test[eid])
        test_mask = np.array([entity in test_entities for entity in ds.entity_ids])
        val_idx, test_idx = np.flatnonzero(~test_mask), np.flatnonzero(test_mask)
    else:
        perm = rng.permutation(n)
        val_idx, test_idx = np.sort(perm[: n // 2]), np.sort(perm[n // 2:])
    dict_ids = np.sort(rng.choice(n, size=max(1, int(round(overlap * n))), replace=False))
    if dict_extra_ratio < 0 or not math.isfinite(dict_extra_ratio):
        raise ValueError("dict_extra_ratio must be a finite non-negative number")
    extra_count = int(round(dict_extra_ratio * n))
    dict_norm = [ds.norm[int(i)] for i in dict_ids]
    distractors = [f"rq2_distractor_{seed}_{i}" for i in range(extra_count)]
    dict_ids = np.concatenate([dict_ids, -np.arange(1, extra_count + 1, dtype=int)])
    dict_norm.extend(distractors)
    victim_ids = rng.choice(n, size=n_records, p=ds.weights)
    victim_norm = []
    for entity_index in victim_ids:
        variants = (ds.noisy_records_by_entity or {}).get(int(entity_index))
        victim_norm.append(variants[int(rng.integers(len(variants)))] if variants else b_norm[entity_index])
    in_dict = set(int(e) for e in dict_ids if int(e) >= 0)
    if ds.counts is not None:
        aux_counts = {e: int(ds.counts[e]) for e in in_dict}
    else:
        aux_counts = {e: 0 for e in in_dict}
        for e in rng.choice(n, size=n_records, p=ds.weights):
            if int(e) in aux_counts:
                aux_counts[int(e)] += 1
    bloom = (ds.linkage.config if ds.linkage is not None else RQ2_CONFIG).bloom
    pad_char = bloom.pad_char
    key = bytes.fromhex(bloom.hmac_key)
    encoder = BloomFilterEncoder(bloom.l, bloom.k, q, key, pad_char)
    # public document frequency of every q-gram (weighted by public entity counts)
    tot = max(1, sum(aux_counts.values()))
    gram_w = {}
    for e, text in zip(dict_ids, dict_norm):
        if int(e) < 0:
            continue
        w = aux_counts[int(e)] / tot
        for g in encoder.grams(text):
            gram_w[g] = gram_w.get(g, 0.0) + w
    aux_grams = sorted(gram_w)
    aux_df = np.array([gram_w[g] for g in aux_grams])
    return Scenario(seed, noise, overlap, key, pad_char, b_norm, val_idx, test_idx, dict_ids, dict_norm,
                    dict_extra_ratio,
                    victim_ids, victim_norm, aux_counts, aux_grams, aux_df)


def _tokens(bf: np.ndarray) -> list:
    return [row.tobytes() for row in np.packbits(bf, axis=1)]


def _base_row(method, l, k, q, scen):
    return {"method": method, "l": l, "k": k, "q": q, "noise": scen.noise, "seed": scen.seed,
            "overlap": scen.overlap, "dict_extra_ratio": scen.dict_extra_ratio,
            "dict_size": len(scen.dict_ids)}


def run_bloom(ds, scen: Scenario, l: int, k: int, q: int = DEFAULT_Q,
              eps: float = math.inf, bit_top: int = RQ2_CONFIG.sweep.bit_top,
              taus=matching.TAU_GRID, *, primary_tau: float | None = None) -> dict:
    validate_dataset(ds)
    eps = validate_epsilon(eps)
    bit_top = validate_bit_top(bit_top)
    enc = BloomFilterEncoder(l, k, q, scen.key, scen.pad_char)
    atk_rng = make_rng(scen.seed, f"rq2:attack:{l}:{k}")
    dp_rng = make_rng(scen.seed, f"rq2:response:{l}:{k}:{eps}")

    bf_a = enc.encode_many(ds.norm)
    bf_b = enc.encode_many(scen.b_norm)
    bf_v = enc.encode_many(scen.victim_norm)                           # one row per stored record
    dict_bf = enc.encode_many(scen.dict_norm)                          # attacker encodes clean dictionary
    if not math.isinf(eps):
        bf_a = randomized_response(bf_a, eps, k, dp_rng)
        bf_b = randomized_response(bf_b, eps, k, dp_rng)
        bf_v = randomized_response(bf_v, eps, k, dp_rng)
    row = _base_row("bloom", l, k, q, scen)
    if not math.isinf(eps):
        row.update(eps=eps, flip_p=flip_probability(eps, k))

    # ---- utility: tune tau on val split, report on test split ----
    D = dice_matrix(bf_a, bf_b)
    v, t = scen.val_idx, scen.test_idx
    tuned = matching.tune_cross_party_thresholds(D[np.ix_(v, v)], taus)
    tau_unc = tuned["tau_unc"]
    tau_c01 = tuned["tau_c01"]
    tau_c05 = tuned["tau_c05"]
    feasible_01 = tuned["feasible_01"]
    feasible_05 = tuned["feasible_05"]

    D_test = D[np.ix_(t, t)]
    # Unconstrained metrics (always present)
    m_unc = matching.cross_party_metrics_at(D_test, tau_unc)
    auc, sep = matching.auc_and_separation(D_test)
    row.update(
        tau_unc=tau_unc,
        f1_unc=m_unc["f1"],
        precision_unc=m_unc["precision"],
        recall_unc=m_unc["recall"],
        fpr_unc=m_unc["fpr"],
    )
    # Constrained at FPR<=0.01
    row["feasible_01"] = feasible_01
    if feasible_01 and tau_c01 is not None:
        m_01 = matching.cross_party_metrics_at(D_test, tau_c01)
        row.update(tau_01=tau_c01, f1_01=m_01["f1"], fpr_01=m_01["fpr"])
    else:
        row.update(tau_01=float("nan"), f1_01=0.0, fpr_01=float("nan"))
    # Constrained at FPR<=0.05
    row["feasible_05"] = feasible_05
    if feasible_05 and tau_c05 is not None:
        m_05 = matching.cross_party_metrics_at(D_test, tau_c05)
        row.update(tau_05=tau_c05, f1_05=m_05["f1"], fpr_05=m_05["fpr"])
    else:
        row.update(tau_05=float("nan"), f1_05=0.0, fpr_05=float("nan"))
    row.update(
        tau=tau_unc,
        precision=m_unc["precision"],
        recall=m_unc["recall"],
        f1=m_unc["f1"],
        fpr=m_unc["fpr"],
        auc=auc,
        sep=sep,
        cross_party_tau=tau_unc,
        **{f"cross_party_{metric}": value for metric, value in m_unc.items()},
    )
    if ds.linkage is not None:
        row.update(evaluate_bloom_linkage(
            ds.linkage, scen.noise, l, k, q, taus, tau=primary_tau,
            post_transform=response_transform(scen.seed, l, k, eps),
        ))

    # ---- privacy ----
    row.update(attacks.reid_attack(bf_b, np.arange(ds.n), dict_bf, scen.dict_ids))
    row["freq_success"] = attacks.frequency_attack(_tokens(bf_v), scen.victim_ids, scen.aux_counts, atk_rng)
    bs, bb, bq = attacks.bit_qgram_attack(bf_v, enc, scen.aux_grams, scen.aux_df, bit_top, atk_rng)
    row.update(bit_success=bs, bit_baseline=bb, bit_qgrams_per_bit=bq)

    # ---- structural ----
    nq = float(np.mean([len(enc.grams(s)) for s in ds.norm]))
    load = metrics.collision_load(nq, k, l)
    fm, fs = metrics.fill_stats(bf_a)
    row.update(fill=fm, fill_std=fs, fill_expected=metrics.expected_fill(load), entropy=metrics.bit_entropy(bf_a),
               load=load, nq_mean=nq)
    row["degenerate"] = int(fm > RQ2_CONFIG.sweep.degenerate_fill)
    return row


def run_exact(ds, scen: Scenario, q: int = DEFAULT_Q) -> dict:
    """Exact matching baseline: HMAC-SHA256(secret salt, normalized string)."""
    validate_dataset(ds)
    def tok(s):
        return keyed_sha256(s, scen.key)

    tok_a = [tok(s) for s in ds.norm]
    tok_b = [tok(s) for s in scen.b_norm]
    tok_v = [tok(s) for s in scen.victim_norm]
    t = scen.test_idx
    row = _base_row("exact_hash", 0, 0, q, scen)
    m = matching.cross_party_exact_metrics([tok_a[i] for i in t], [tok_b[i] for i in t])
    row.update(tau=float("nan"), precision=m["precision"], recall=m["recall"], f1=m["f1"], fpr=m["fpr"],
               auc=float("nan"), sep=float("nan"), cross_party_tau=float("nan"),
               **{f"cross_party_{metric}": value for metric, value in m.items()})
    if ds.linkage is not None:
        linkage = ds.linkage
        linker = ExactLinker("normalized_exact", linkage.field_set, True, linkage.config)
        row.update(evaluate_test_clusters(linkage, linker))
    row.update(
        tau_unc=float("nan"), precision_unc=m["precision"], recall_unc=m["recall"],
        f1_unc=m["f1"], fpr_unc=m["fpr"],
        feasible_01=True, tau_01=float("nan"), f1_01=m["f1"], fpr_01=m["fpr"],
        feasible_05=True, tau_05=float("nan"), f1_05=m["f1"], fpr_05=m["fpr"],
        degenerate=0,
    )
    dict_tokens = [tok(s) for s in scen.dict_norm]
    row.update(attacks.exact_reid_attack(tok_b, np.arange(ds.n), dict_tokens, scen.dict_ids))
    atk_rng = make_rng(scen.seed, "rq2:exact-frequency")
    row["freq_success"] = attacks.frequency_attack(tok_v, scen.victim_ids, scen.aux_counts, atk_rng)
    row.update(bit_success=float("nan"), bit_baseline=float("nan"), bit_qgrams_per_bit=float("nan"),
               fill=float("nan"), fill_std=float("nan"), fill_expected=float("nan"), entropy=float("nan"),
               load=float("nan"), nq_mean=float("nan"))
    return row
