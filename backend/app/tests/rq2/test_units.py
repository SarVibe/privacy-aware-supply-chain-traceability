import math

import numpy as np
from src.rq2 import attacks, matching, metrics
from src.rq2.bloom import BloomEncoder
from src.rq2.data import load_dataset, synthetic_dataset
from src.rq2.dp import flip_probability, randomized_response
from src.rq2.noise import add_noise, add_typos
from src.rq2.preprocess import normalize
from src.rq2.qgrams import qgram_set, qgrams
from src.config import Config

KEY = b"k" * 32


def test_normalize_variants_collapse():
    for s in ["Paracetamol-500mg", "paracetamol 500 mg", "PARACETAMOL_500MG"]:
        assert normalize(s) == "paracetamol500mg"
    assert normalize(None) == ""


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


def test_qgrams():
    assert qgrams("abcd", 2) == ["ab", "bc", "cd"]
    assert qgram_set("aaa", 2) == {"aa"}
    assert qgrams("a", 2) == ["a"]
    assert qgrams("ab", 2, pad=True) == ["_a", "ab", "b_"]


def test_positions_distinct_and_in_range():
    for l in (256, 1024):
        enc = BloomEncoder(l, 30, KEY)
        pos = enc.gram_positions([a + b for a in "abcde" for b in "fghij"])
        assert pos.min() >= 0 and pos.max() < l
        assert all(len(set(row)) == 30 for row in pos)      # k distinct bits per q-gram (power-of-two l)


def test_encoder_deterministic_and_keyed():
    a, b = BloomEncoder(512, 4, KEY), BloomEncoder(512, 4, KEY)
    assert (a.encode("lamivudine150mg") == b.encode("lamivudine150mg")).all()
    other = BloomEncoder(512, 4, b"z" * 32)
    assert (a.encode("lamivudine150mg") != other.encode("lamivudine150mg")).any()


def test_encode_many_matches_single_and_handles_duplicates():
    enc = BloomEncoder(256, 4, KEY)
    strs = ["abcdef", "abcdef", "xyz"]
    m = enc.encode_many(strs)
    assert m.shape == (3, 256) and (m[0] == m[1]).all()
    assert (m[2] == enc.encode("xyz")).all()


def test_fill_matches_theory():
    ds = synthetic_dataset(300, seed=1)
    enc = BloomEncoder(1024, 4, KEY)
    bf = enc.encode_many(ds.norm)
    nq = np.mean([len(qgram_set(s)) for s in ds.norm])
    exp = metrics.expected_fill(metrics.collision_load(nq, 4, 1024))
    assert abs(bf.mean() - exp) < 0.02


def test_dice_properties():
    x = np.array([[1, 1, 0, 0], [1, 0, 1, 0]], dtype=np.uint8)
    D = matching.dice_matrix(x, x)
    assert D[0, 0] == 1.0 and abs(D[0, 1] - 0.5) < 1e-12
    assert matching.dice_matrix(np.zeros((1, 4), np.uint8), x).sum() == 0


def test_threshold_tuning_and_metrics():
    D = np.array([[0.95, 0.2, 0.3], [0.1, 0.9, 0.4], [0.3, 0.2, 0.85]])  # perfectly separable
    tau = matching.tune_tau(D)
    m = matching.metrics_at(D, tau)
    assert m["f1"] == 1.0 and 0.41 <= tau <= 0.85
    auc, sep = matching.auc_and_separation(D)
    assert auc == 1.0 and sep > 0.5
    assert matching.metrics_at(D, 0.99)["recall"] == 0.0


def test_exact_metrics():
    a = [b"x", b"y", b"z"]
    b = [b"x", b"q", b"z"]
    m = matching.exact_metrics(a, b)
    assert m["precision"] == 1.0 and abs(m["recall"] - 2 / 3) < 1e-12


def test_noise_changes_strings_at_requested_rate():
    rng = np.random.default_rng(0)
    assert add_typos("abcdef", 0.0, rng) == "abcdef"
    out = add_noise(["lamivudine150mg"] * 50, 0.3, rng)
    assert sum(o != "lamivudine150mg" for o in out) >= 45


def test_dp_flip_rate():
    k, eps = 4, 8.0
    p = flip_probability(eps, k)
    assert abs(p - 1 / (1 + math.exp(2))) < 1e-12 and flip_probability(math.inf, k) == 0
    bf = np.zeros((200, 1000), dtype=np.uint8)
    flipped = randomized_response(bf, eps, k, np.random.default_rng(0))
    assert abs(flipped.mean() - p) < 0.005


def test_reid_attack_collisions_reduce_success():
    ds = synthetic_dataset(200, seed=3)
    ids = np.arange(ds.n)
    res = {}
    for l, k in [(2048, 2), (64, 8)]:
        enc = BloomEncoder(l, k, KEY)
        bf = enc.encode_many(ds.norm)
        res[l] = attacks.reid_attack(bf, ids, bf, ids)
    assert res[2048]["reid_top1"] > 0.95 and res[2048]["reid_cands_delta"] < 3
    assert res[64]["reid_top1"] < res[2048]["reid_top1"] - 0.3
    assert res[64]["reid_cands_delta"] > res[2048]["reid_cands_delta"]


def test_reid_attack_respects_dictionary_coverage():
    ds = synthetic_dataset(100, seed=4)
    enc = BloomEncoder(2048, 2, KEY)
    bf = enc.encode_many(ds.norm)
    dict_ids = np.arange(50)
    r = attacks.reid_attack(bf, np.arange(100), bf[dict_ids], dict_ids)
    assert abs(r["dict_coverage"] - 0.5) < 1e-12 and r["reid_top1"] <= 0.5 + 1e-9


def test_exact_reid_attack():
    r = attacks.exact_reid_attack([b"a", b"b", b"c"], [0, 1, 2], [b"a", b"b"], [0, 1])
    assert abs(r["reid_top1"] - 2 / 3) < 1e-12


def test_frequency_attack_perfect_with_distinct_frequencies():
    truth = np.array([0] * 50 + [1] * 30 + [2] * 10)
    tokens = [bytes([int(t)]) for t in truth]
    aux = {0: 500, 1: 300, 2: 100}
    assert attacks.frequency_attack(tokens, truth, aux, np.random.default_rng(0)) == 1.0
    merged = [b"same"] * len(truth)            # complete collision -> only the top entity can be right
    assert attacks.frequency_attack(merged, truth, aux, np.random.default_rng(0)) == 50 / 90


def test_bit_qgram_attack_runs_and_beats_baseline_at_low_collision():
    ds = synthetic_dataset(300, seed=5)
    enc = BloomEncoder(2048, 2, KEY)
    bf = enc.encode_many(ds.norm)
    grams, df = {}, {}
    for s in ds.norm:
        for g in qgram_set(s):
            df[g] = df.get(g, 0) + 1 / len(ds.norm)
    succ, base, qpb = attacks.bit_qgram_attack(bf, enc, sorted(df), [df[g] for g in sorted(df)], 50,
                                               np.random.default_rng(0))
    assert 0 <= succ <= 1 and succ > base and qpb >= 1


def test_structural_metrics():
    bf = np.array([[1, 0, 1, 0], [1, 1, 0, 0]], dtype=np.uint8)
    assert metrics.fill_stats(bf)[0] == 0.5
    assert 0 < metrics.bit_entropy(bf) <= 1
    assert abs(metrics.expected_fill(metrics.collision_load(10, 4, 1024)) - (1 - math.exp(-40 / 1024))) < 1e-12
