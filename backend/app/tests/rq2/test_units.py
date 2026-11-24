import math

import numpy as np
from src.rq2 import privacy_attacks as attacks
from src.rq2 import similarity_matching as matching
from src.rq2 import privacy_metrics as metrics
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.similarity.dice import dice_matrix
from src.rq2.rq2_dataset import load_dataset, synthetic_dataset
from src.rq2.numpy_randomized_response import flip_probability, randomized_response
from src.application_config import Config

KEY = b"k" * 32


def test_real_dataset_description_and_composite_aliases():
    description = load_dataset(
        str(Config.RAW_DATA_PATH),
        "raw_item_description",
        n=20,
        seed=0,
    )
    composite = load_dataset(
        str(Config.RAW_DATA_PATH),
        "raw_item_description",
        n=20,
        seed=0,
        composite_columns=["dosage", "dosage_form", "pack_size"],
    )

    assert description.n == 20
    assert composite.n == 20
    assert ":description" in description.source
    assert ":composite" in composite.source
    assert all(len(text) > 0 for text in composite.raw)


def test_fill_matches_theory():
    ds = synthetic_dataset(200, seed=1)
    enc = BloomFilterEncoder(1024, 4, 2, KEY, "_")
    bf = enc.encode_many(ds.norm)
    nq = np.mean([len(enc.grams(s)) for s in ds.norm])
    exp = metrics.expected_fill(metrics.collision_load(nq, 4, 1024))
    assert abs(bf.mean() - exp) < 0.02


def test_dice_properties():
    x = np.array([[1, 1, 0, 0], [1, 0, 1, 0]], dtype=np.uint8)
    D = dice_matrix(x, x)
    assert D[0, 0] == 1.0 and abs(D[0, 1] - 0.5) < 1e-12
    assert dice_matrix(np.zeros((1, 4), np.uint8), x).sum() == 0


def test_threshold_tuning_and_metrics():
    D = np.array([[0.95, 0.2, 0.3], [0.1, 0.9, 0.4], [0.3, 0.2, 0.85]])  # perfectly separable
    tau = matching.select_cross_party_threshold(D)
    m = matching.cross_party_metrics_at(D, tau)
    assert m["f1"] == 1.0 and 0.30 <= tau <= 0.99
    auc, sep = matching.auc_and_separation(D)
    assert auc == 1.0 and sep > 0.5
    assert matching.cross_party_metrics_at(D, 0.99)["recall"] == 0.0


def test_tune_tau_full_basic():
    """tune_tau_full returns the expected structure and tau_unc is always present."""
    D = np.array([[0.95, 0.2, 0.3], [0.1, 0.9, 0.4], [0.3, 0.2, 0.85]])
    result = matching.tune_cross_party_thresholds(D)
    assert "tau_unc" in result
    assert "tau_c01" in result
    assert "tau_c05" in result
    assert "feasible_01" in result
    assert "feasible_05" in result
    # For a separable matrix, unconstrained F1 should be 1.0
    m = matching.cross_party_metrics_at(D, result["tau_unc"])
    assert m["f1"] == 1.0


def test_tune_tau_full_saturated_infeasible():
    """For a saturated / degenerate similarity matrix, feasible_01 should be False."""
    # All-ones matrix: every pair looks like a match (FPR = 1.0 for any tau < max)
    n = 10
    D_sat = np.ones((n, n), dtype=float)
    result = matching.tune_cross_party_thresholds(D_sat)
    # tau_unc must still be a valid float (never raises)
    assert isinstance(result["tau_unc"], float)
    # For a fully saturated matrix, FPR can't be <= 0.01 at any threshold
    assert result["feasible_01"] == False
    assert result["tau_c01"] is None


def test_tune_tau_never_raises_on_saturated():
    """tune_tau (backward compat) must never raise even for saturated inputs."""
    n = 8
    D_sat = np.ones((n, n), dtype=float)
    tau = matching.select_cross_party_threshold(D_sat)
    assert isinstance(tau, float) and 0.30 <= tau <= 0.99


def test_cross_party_exact_metrics():
    a = [b"x", b"y", b"z"]
    b = [b"x", b"q", b"z"]
    m = matching.cross_party_exact_metrics(a, b)
    assert m["precision"] == 1.0 and abs(m["recall"] - 2 / 3) < 1e-12


def test_dp_flip_rate():
    k, eps = 4, 8.0
    p = flip_probability(eps, k)
    assert abs(p - 1 / (1 + math.exp(2))) < 1e-12 and flip_probability(math.inf, k) == 0
    bf = np.zeros((200, 1000), dtype=np.uint8)
    flipped = randomized_response(bf, eps, k, np.random.default_rng(0))
    assert abs(flipped.mean() - p) < 0.005
    assert flip_probability(10000.0, k) == 0.0


def test_reid_attack_collisions_reduce_success():
    ds = synthetic_dataset(200, seed=3)
    ids = np.arange(ds.n)
    res = {}
    for l, k in [(2048, 2), (64, 8)]:
        enc = BloomFilterEncoder(l, k, 2, KEY, "_")
        bf = enc.encode_many(ds.norm)
        res[l] = attacks.reid_attack(bf, ids, bf, ids)
    assert res[2048]["reid_top1"] > 0.95 and res[2048]["reid_cands_delta"] <= 1.0
    assert res[64]["reid_top1"] < res[2048]["reid_top1"] - 0.3
    assert res[64]["reid_cands_delta"] > res[2048]["reid_cands_delta"]


def test_reid_attack_respects_dictionary_coverage():
    ds = synthetic_dataset(100, seed=4)
    enc = BloomFilterEncoder(2048, 2, 2, KEY, "_")
    bf = enc.encode_many(ds.norm)
    dict_ids = np.arange(50)
    r = attacks.reid_attack(bf, np.arange(100), bf[dict_ids], dict_ids)
    assert abs(r["dict_coverage"] - 0.5) < 1e-12 and r["reid_top1"] <= 0.5 + 1e-9


def test_exact_reid_attack():
    r = attacks.exact_reid_attack([b"a", b"a", b"c"], [0, 2, 3], [b"a", b"a"], [0, 1])
    assert r["reid_top1"] == 0.5 / 3
    assert r["reid_top1_conditional"] == 0.5 / 2
    assert r["reid_ties"] == r["reid_cands_delta"] == 2


def test_frequency_attack_perfect_with_distinct_frequencies():
    truth = np.array([0] * 50 + [1] * 30 + [2] * 10)
    tokens = [bytes([int(t)]) for t in truth]
    aux = {0: 500, 1: 300, 2: 100}
    assert attacks.frequency_attack(tokens, truth, aux, np.random.default_rng(0)) == 1.0
    merged = [b"same"] * len(truth)            # complete collision -> only the top entity can be right
    assert attacks.frequency_attack(merged, truth, aux, np.random.default_rng(0)) == 50 / 90


def test_bit_qgram_attack_runs_and_beats_baseline_at_low_collision():
    ds = synthetic_dataset(200, seed=5)
    enc = BloomFilterEncoder(2048, 2, 2, KEY, "_")
    bf = enc.encode_many(ds.norm)
    df = {}
    for s in ds.norm:
        for g in enc.grams(s):
            df[g] = df.get(g, 0) + 1 / len(ds.norm)
    succ, base, qpb = attacks.bit_qgram_attack(bf, enc, sorted(df), [df[g] for g in sorted(df)], 50,
                                               np.random.default_rng(0))
    assert 0 <= succ <= 1 and succ > base and qpb >= 1


def test_structural_metrics():
    bf = np.array([[1, 0, 1, 0], [1, 1, 0, 0]], dtype=np.uint8)
    assert metrics.fill_stats(bf)[0] == 0.5
    assert 0 < metrics.bit_entropy(bf) <= 1
    assert abs(metrics.expected_fill(metrics.collision_load(10, 4, 1024)) - (1 - math.exp(-40 / 1024))) < 1e-12
