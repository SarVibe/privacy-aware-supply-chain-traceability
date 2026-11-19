"""One experimental run = Scenario (data-side randomness) x configuration (l, k, eps).

Scenario (depends on seed, noise, overlap only -> identical across (l, k), so
configurations are compared on *paired* data):
  * B = typo-corrupted copy of the N entities (party B); A = the clean entities.
  * a validation/test split of the N entity pairs (tau tuned on val, reported on test).
  * the attacker's public dictionary (a fraction `overlap` of the entities).
  * M stored victim records (Zipf-sampled entities, typos applied per record) and an
    independent public frequency sample used by the frequency attacks.
"""
import hashlib
import hmac
import math
from dataclasses import dataclass

import numpy as np

from . import privacy_attacks as attacks
from . import similarity_matching as matching
from . import privacy_metrics as metrics
from .experiment_config import (BIT_ATTACK_TOP_BITS, DEFAULT_PAD, DEFAULT_Q)
from src.rq2.bloom_encoder import BloomEncoder
from src.rq2.numpy_randomized_response import flip_probability, randomized_response
from src.common.noise_injection import add_noise, NoiseSpec
from src.rq2.text_normalizer import normalize
from src.rq2.qgram_utils import qgram_set
from .parameter_validation import (validate_noise, validate_overlap, validate_n_records, validate_eps,
                       validate_dataset, validate_dictionary, validate_bit_top)


@dataclass
class Scenario:
    seed: int
    noise: float
    overlap: float
    key: bytes
    b_norm: list
    val_idx: np.ndarray
    test_idx: np.ndarray
    dict_ids: np.ndarray
    victim_ids: np.ndarray
    victim_norm: list
    aux_counts: dict
    aux_grams: list
    aux_df: np.ndarray


def build_scenario(ds, seed: int, noise: float, overlap: float = 1.0, n_records: int = 3000,
                   q: int = DEFAULT_Q, pad: bool = DEFAULT_PAD) -> Scenario:
    validate_dataset(ds)
    noise = validate_noise(noise)
    overlap = validate_overlap(overlap)
    n_records = validate_n_records(n_records)
    rng = np.random.default_rng(np.random.SeedSequence([seed, int(round(noise * 10000)), int(round(overlap * 100))]))
    n = ds.n
    if getattr(ds, "noisy_norm", None) is not None:
        b_norm = list(ds.noisy_norm)
    else:
        b_norm = [normalize(s) for s in add_noise(ds.raw, noise, rng)]
    perm = rng.permutation(n)
    val_idx, test_idx = np.sort(perm[: n // 2]), np.sort(perm[n // 2:])
    dict_ids = np.sort(rng.choice(n, size=max(1, int(round(overlap * n))), replace=False))
    victim_ids = rng.choice(n, size=n_records, p=ds.weights)
    if getattr(ds, "noisy_norm", None) is not None:
        noisy_records_by_entity = getattr(ds, "noisy_records_by_entity", None)
        victim_norm = []
        for entity_index in victim_ids:
            entity_index = int(entity_index)
            variants = (
                noisy_records_by_entity.get(entity_index)
                if noisy_records_by_entity is not None
                else None
            )
            if variants:
                victim_norm.append(str(variants[int(rng.integers(len(variants)))]))
            else:
                victim_norm.append(ds.noisy_norm[entity_index])
    else:
        victim_raw = add_noise([ds.raw[i] for i in victim_ids], noise, rng)
        victim_norm = [normalize(s) for s in victim_raw]
    aux_sample = rng.choice(n, size=n_records, p=ds.weights)          # public clean frequency sample
    in_dict = set(int(e) for e in dict_ids)
    if getattr(ds, "counts", None) is not None:
        aux_counts = {int(e): int(ds.counts[int(e)]) for e in in_dict}
    else:
        aux_counts = {e: 0 for e in in_dict}
    if getattr(ds, "counts", None) is None:
        aux_sample = rng.choice(n, size=n_records, p=ds.weights)
        for e in aux_sample:
            if int(e) in aux_counts:
                aux_counts[int(e)] += 1
    # public document frequency of every q-gram (weighted by public entity counts)
    tot = max(1, sum(aux_counts.values()))
    gram_w = {}
    for e in dict_ids:
        w = aux_counts[int(e)] / tot
        for g in qgram_set(ds.norm[int(e)], q, pad):
            gram_w[g] = gram_w.get(g, 0.0) + w
    aux_grams = sorted(gram_w)
    aux_df = np.array([gram_w[g] for g in aux_grams])
    key = hashlib.sha256(f"rq2-key-{seed}".encode()).digest()
    return Scenario(seed, noise, overlap, key, b_norm, val_idx, test_idx, dict_ids, victim_ids,
                    victim_norm, aux_counts, aux_grams, aux_df)


def _tokens(bf: np.ndarray) -> list:
    return [row.tobytes() for row in np.packbits(bf, axis=1)]


def _base_row(method, l, k, q, scen, eps):
    return {"method": method, "l": l, "k": k, "q": q, "noise": scen.noise, "seed": scen.seed,
            "overlap": scen.overlap, "eps": eps}


def run_bloom(ds, scen: Scenario, l: int, k: int, q: int = DEFAULT_Q, pad: bool = DEFAULT_PAD,
              eps: float = math.inf, bit_top: int = BIT_ATTACK_TOP_BITS) -> dict:
    validate_dataset(ds)
    eps = validate_eps(eps)
    bit_top = validate_bit_top(bit_top)
    if k > l:
        raise ValueError("k must be <= l")
    enc = BloomEncoder(l, k, scen.key, q, pad)
    dp_rng = np.random.default_rng(np.random.SeedSequence([scen.seed, 77, l, k, int(min(eps, 1e6) * 100)]))
    atk_rng = np.random.default_rng(np.random.SeedSequence([scen.seed, 99, l, k]))

    bf_a = enc.encode_many(ds.norm)
    bf_b = enc.encode_many(scen.b_norm)
    bf_v = enc.encode_many(scen.victim_norm)                           # one row per stored record
    dict_bf = bf_a[scen.dict_ids]                                      # attacker encodes clean dictionary
    if not math.isinf(eps):                                            # DP applied before storage
        bf_a = randomized_response(bf_a, eps, k, dp_rng)
        bf_b = randomized_response(bf_b, eps, k, dp_rng)
        bf_v = randomized_response(bf_v, eps, k, dp_rng)
        dict_bf = enc.encode_many([ds.norm[int(e)] for e in scen.dict_ids])  # attacker's own BFs stay clean

    row = _base_row("bloom", l, k, q, scen, eps)
    row["flip_p"] = flip_probability(eps, k)

    # ---- utility: tune tau on val split, report on test split ----
    D = matching.dice_matrix(bf_a, bf_b)
    v, t = scen.val_idx, scen.test_idx
    tau = matching.tune_tau(D[np.ix_(v, v)])
    D_test = D[np.ix_(t, t)]
    m = matching.metrics_at(D_test, tau)
    auc, sep = matching.auc_and_separation(D_test)
    row.update(tau=tau, precision=m["precision"], recall=m["recall"], f1=m["f1"], fpr=m["fpr"], auc=auc, sep=sep)

    # ---- privacy ----
    row.update(attacks.reid_attack(bf_b, np.arange(ds.n), dict_bf, scen.dict_ids))
    row["freq_success"] = attacks.frequency_attack(_tokens(bf_v), scen.victim_ids, scen.aux_counts, atk_rng)
    bs, bb, bq = attacks.bit_qgram_attack(bf_v, enc, scen.aux_grams, scen.aux_df, bit_top, atk_rng)
    row.update(bit_success=bs, bit_baseline=bb, bit_qgrams_per_bit=bq)

    # ---- structural ----
    nq = float(np.mean([len(qgram_set(s, q, pad)) for s in ds.norm]))
    load = metrics.collision_load(nq, k, l)
    fm, fs = metrics.fill_stats(bf_a)
    row.update(fill=fm, fill_std=fs, fill_expected=metrics.expected_fill(load), entropy=metrics.bit_entropy(bf_a),
               load=load, nq_mean=nq)
    return row


def run_exact(ds, scen: Scenario, q: int = DEFAULT_Q) -> dict:
    """Exact matching baseline: HMAC-SHA256(secret salt, normalized string)."""
    validate_dataset(ds)
    def tok(s):
        return hmac.new(scen.key, s.encode(), hashlib.sha256).digest()

    tok_a = [tok(s) for s in ds.norm]
    tok_b = [tok(s) for s in scen.b_norm]
    tok_v = [tok(s) for s in scen.victim_norm]
    t = scen.test_idx
    row = _base_row("exact_hash", 0, 0, q, scen, math.inf)
    m = matching.exact_metrics([tok_a[i] for i in t], [tok_b[i] for i in t])
    row.update(tau=float("nan"), precision=m["precision"], recall=m["recall"], f1=m["f1"], fpr=m["fpr"],
               auc=float("nan"), sep=float("nan"), flip_p=0.0)
    dict_tokens = [tok_a[int(e)] for e in scen.dict_ids]
    row.update(attacks.exact_reid_attack(tok_b, np.arange(ds.n), dict_tokens, scen.dict_ids))
    atk_rng = np.random.default_rng(np.random.SeedSequence([scen.seed, 98]))
    row["freq_success"] = attacks.frequency_attack(tok_v, scen.victim_ids, scen.aux_counts, atk_rng)
    row.update(bit_success=float("nan"), bit_baseline=float("nan"), bit_qgrams_per_bit=float("nan"),
               fill=float("nan"), fill_std=float("nan"), fill_expected=float("nan"), entropy=float("nan"),
               load=float("nan"), nq_mean=float("nan"))
    return row
