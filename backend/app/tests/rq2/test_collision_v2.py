import hashlib
import hmac
from dataclasses import replace
from math import log

import numpy as np
import pandas as pd
import pytest

from src.common.data.loader import load_noisy
from src.common.encoding.bloom_filter import fill_ratio
from src.common.linking.bloom import PreparedBloom
from src.rq2.collision_cohorts import build_seed_partition, encoder_for_cell, load_collision_cohorts
from src.rq2.collision_privacy import FrequencyEvaluation, fingerprint_collision_proxy
from src.rq2.collision_v2_analysis import select_v2_validation
from src.rq2.collision_v2_artifacts import validate_v2_table
from src.rq2.collision_v2_config import load_v2_protocol, v2_keys
from src.rq2.collision_v2_metrics import (
    diagnose_edges, finite_candidate_probability, known_key_metrics, matched_frequency, v2_occupancy,
)
from src.rq2.collision_v2_runs import V2Runs, evaluate_v2_cell


class ToyPositions:
    def gram_positions(self, tokens):
        positions = {"a": [0, 0], "b": [1, 2], "c": [0, 1], "d": [0, 0]}
        return np.array([positions[token] for token in tokens])


def toy_evaluation():
    records = [{"a"}, {"a", "c"}]
    bits = np.array([[1, 0, 0, 0], [1, 1, 0, 0]], dtype=np.uint8)
    reference = {"a": 0.8, "c": 0.2}
    target = {"a": 1.0, "b": 0.5, "c": 0.5, "d": 0.25}
    evaluator = FrequencyEvaluation.from_records(bits, target, reference, ToyPositions())
    return records, bits, reference, evaluator


def test_v2_hand_scoring_separate_random_pools_and_repeated_positions():
    _, _, reference, evaluator = toy_evaluation()
    scores = matched_frequency(evaluator, reference, 100, "toy")
    assert scores["used_bits"] == 2
    assert scores["hit"] == 1
    assert scores["null_full"] == 5 / 8
    assert scores["null_matched"] == 3 / 4
    assert scores["excess_matched"] == 1 / 4
    assert scores["lift_matched"] == pytest.approx(4 / 3)
    row = {"variant": "description", "noise": 0.15, "seed": 100, "l": 4, "k": 2,
           "split": "test", "frequency_source": "reference", **scores}
    assert len(validate_v2_table("e1", pd.DataFrame([row]))) == 1
    with pytest.raises(ValueError, match="duplicate"):
        validate_v2_table("e1", pd.DataFrame([row, row]))


def test_v2_known_key_candidates_and_no_false_negative():
    records, bits, _, evaluator = toy_evaluation()
    measures = known_key_metrics(bits, records, evaluator)
    assert measures["e2_precision_mean"] == pytest.approx((1 / 2 + 2 / 3) / 2)
    assert measures["e2_precision_median"] == measures["e2_precision_mean"]
    assert measures["e2_false_candidates"] == 1
    assert measures["e2_exact_recovery"] == 0
    with pytest.raises(AssertionError, match="inserted"):
        known_key_metrics(np.zeros_like(bits), records, evaluator)


def test_v2_finite_length_expected_fill_and_candidate_probability(golden_config):
    rng = np.random.default_rng(14)
    length, hashes = 64, 4
    counts = np.repeat([2, 20], 2500)
    encoded = np.zeros((len(counts), length), np.uint8)
    for row, count in zip(encoded, counts, strict=True):
        row[rng.integers(length, size=count * hashes)] = 1
    predicted = (1 - (1 - 1 / length) ** (hashes * counts)).mean()
    assert fill_ratio(encoded).mean() == pytest.approx(predicted, abs=0.004)
    simulated = np.mean(fill_ratio(encoded) ** hashes)
    assert finite_candidate_probability(counts, length, hashes).mean() == pytest.approx(simulated, abs=0.004)
    assert finite_candidate_probability(np.array([1]), 2, 2)[0] == pytest.approx(0.625)
    tokens, bits, _, evaluator = toy_evaluation()
    recordwise = (1 - (1 - 1 / 4) ** (2 * np.array([1, 2]))).mean()
    assert v2_occupancy(bits, tokens, evaluator, 2)["fill_finite"] == pytest.approx(recordwise)


def test_v2_analytical_u_shape_and_optimum():
    length, q_mean = 256, 32
    optimum = length * log(2) / q_mean
    proxy = lambda k: fingerprint_collision_proxy(q_mean, length, k)
    assert proxy(optimum) < min(proxy(optimum - 1), proxy(optimum + 1))
    grid = [proxy(k) for k in (2, 4, 6, 8, 10)]
    assert grid[0] > grid[1] > grid[2] < grid[3] < grid[4]


def test_v2_direct_edges_vs_connected_components():
    ids = pd.Index(["A", "B", "C"])
    prepared = PreparedBloom(ids, np.array([0, 1, 0]), np.array([1, 2, 2]), np.array([0.9, 0.9, 0.2]), 0)
    truth = pd.Series(["E1", "E1", "E2"], index=ids)
    result = diagnose_edges(prepared, truth, 0.8)
    assert result["direct_f1"] == pytest.approx(2 / 3)
    assert result["direct_tp"] == result["cluster_tp"] == 1
    assert result["direct_false"] == result["closure_added_false"] == 1
    assert result["cluster_predicted"] == 3


def test_v2_fixed_key_replay_matches_independent_bit_array(golden_config):
    fixture = bytes(range(32))
    pair = 256, 10
    grams = [{"aa", "bc"}, {"cd"}, {"aa", "bc"}]
    expected = np.zeros((len(grams), pair[0]), dtype=np.uint8)
    key = hmac.digest(fixture, b"rq2:v2:bloom:5", "sha256")
    assert v2_keys(fixture, 5)[0] == key
    assert v2_keys(fixture, 6)[0] != key
    for row, tokens in zip(expected, grams, strict=True):
        for token in tokens:
            for i in range(pair[1]):
                position = int.from_bytes(hmac.digest(key, f"{i}:{token}".encode(), "sha256")[:4], "big") % pair[0]
                row[position] = 1
    expected_digest = hashlib.sha256(expected.tobytes()).digest()
    for _ in range(2):
        replay = encoder_for_cell(golden_config, pair, key).encode_gram_sets(grams)
        assert hashlib.sha256(replay.tobytes()).digest() == expected_digest


def test_v2_validation_selection_applies_budget_and_ignores_test_fields():
    cfg = load_v2_protocol()
    rows = [{"seed": seed, "l": l, "k": k, "f1": f1, "e2_precision_mean": precision, "test_f1": 1.0 - f1}
            for seed in cfg.seeds for l, k, f1, precision in
            ((1024, 4, 0.90, 0.95), (512, 4, 0.88, 0.90), (256, 30, 0.83, 0.05))]
    data = pd.DataFrame(rows)
    chosen, extreme, floor, _ = select_v2_validation(data, cfg)
    assert chosen == (512, 4) and extreme == (256, 30) and floor == pytest.approx(0.85)
    assert select_v2_validation(data.assign(test_f1=0.0), cfg)[0] == chosen


def test_v2_cell_keeps_cutoff_and_selection_endpoint_validation_only(golden_config):
    cfg = load_v2_protocol()
    fixture = bytes(range(32))
    base = load_noisy(0, 0, golden_config)
    split = build_seed_partition(base, golden_config, cfg, 5)
    pair = 256, 4
    cohorts = load_collision_cohorts(base, golden_config, cfg, 5, 0, split,
                                      encoder_for_cell(golden_config, pair, fixture))
    first, second = V2Runs(), V2Runs()
    kwargs = dict(seed=5, noise=0.0, variant="description", pair=pair, key=fixture)
    evaluate_v2_cell(first, cohorts, golden_config, cfg, **kwargs)
    test = cohorts["test"]
    changed = {**cohorts, "test": replace(test, frame=test.frame.assign(entity_id="changed"),
                                          tokens=[{"zz"} for _ in test.tokens])}
    evaluate_v2_cell(second, changed, golden_config, cfg, **kwargs)
    assert first.validation == second.validation
    assert first.tau_sweeps == second.tau_sweeps
