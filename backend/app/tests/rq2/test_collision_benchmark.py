import hashlib
import json
import math
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from src.common.data import loader
from src.common.encoding.bloom_filter import BloomFilterEncoder, fill_ratio
from src.common.evaluation.aggregation import (
    complete_seed_differences, matched_rank_biserial, paired_bootstrap_summary,
)
from src.common.experiment.io import read_csv, write_csv
from src.common.experiment.linkage import evaluate_test_clusters
from src.common.linking.bloom import BloomLinker
from src.common.linking.exact import ExactLinker, NORMALIZED_EXACT
from src.common.noise.typo_noise import inject_noise
from src.common.paths import app_dir
from src.common.preprocessing.field_builder import build_field_strings
from src.common.seeding import make_rng
from src.rq2.collision_cohorts import (
    build_seed_partition, derive_experiment_keys, encoder_for_cell, load_collision_cohorts, load_experiment_root,
)
from src.rq2.collision_config import Controls, load_collision_config
from src.rq2.collision_gate import collision_regression_gate, frozen_hashes
from src.rq2.collision_linkage import cohort_tokens
from src.rq2.collision_privacy import FrequencyEvaluation, expected_occupancy, fingerprint_collision_proxy, insertion_frequencies
from src.rq2.collision_runs import CollisionRuns, attack_control_passed, evaluate_bloom_cell
from src.rq2.collision_schema import GROUP_KEYS, RUN_METRICS, validate_collision_csv, write_collision_csv
from src.rq2.collision_selection import select_collision_config

GOLDEN = Path(__file__).parents[1] / "golden" / "rq1"
TEST_ROOT = bytes(range(32))


def test_gate_uses_exact_metrics_and_preserves_artifacts(tmp_path, golden_config):
    for name in ("raw_runs.csv", "tau_selection.csv"):
        shutil.copyfile(GOLDEN / name, tmp_path / name)
    (tmp_path / "h1_check.md").write_text("Fixture", encoding="utf-8")
    fingerprint = hashlib.sha256(bytes.fromhex(golden_config.bloom.hmac_key)).hexdigest()[:12]
    (tmp_path / "metadata.json").write_text(
        json.dumps({"config": {"bloom": {"hmac_key_fingerprint": fingerprint}}}), encoding="utf-8"
    )
    frozen = read_csv(tmp_path / "raw_runs.csv", round_trip=True)
    mask = frozen["field_set"].eq("composite") & frozen["tau_mode"].eq("single") & frozen["noise_level"].eq(0.15)
    tau = frozen.loc[mask, "tau"].item()
    linkage = loader.load_linkage_data(golden_config, 0, 0.15, "composite")
    # The small checked-in fixture was serialized with truncated precision.
    expected = evaluate_test_clusters(linkage, BloomLinker("bloom_fuzzy", "composite", tau, golden_config))
    for name, value in expected.items():
        frozen.loc[mask, name] = value
    write_csv(frozen, tmp_path / "raw_runs.csv")
    before = frozen_hashes(tmp_path)
    args = golden_config, tmp_path, [0], 0.15, "composite", (1024, 4)
    rows, historical, hashes = collision_regression_gate(*args)
    assert rows["passed"].tolist() == [True]
    assert historical[0] == rows["tau"].iloc[0]
    assert hashes == frozen_hashes(tmp_path) == before
    frozen.loc[mask, "f1"] += 1e-14
    write_csv(frozen, tmp_path / "raw_runs.csv")
    with pytest.raises(ValueError, match="seed 0.*f1"):
        collision_regression_gate(*args)


def test_normalized_keyed_and_unkeyed_exact_cluster_equality(golden_config):
    frame = loader.load_noisy(0, 0.15, golden_config)
    unkeyed = ExactLinker(NORMALIZED_EXACT, "composite", True, golden_config)
    keyed = ExactLinker(NORMALIZED_EXACT, "composite", True, golden_config, key=TEST_ROOT)
    pd.testing.assert_series_equal(unkeyed.link(frame), keyed.link(frame))


def test_fill_formula_matches_encoder_simulation():
    length, hashes, q_mean = 512, 4, 40
    enc = BloomFilterEncoder(length, hashes, 2, TEST_ROOT, "_")
    tokens = [[f"item{record}:{number}" for number in range(q_mean)] for record in range(350)]
    measured = float(fill_ratio(enc.encode_gram_sets(tokens)).mean())
    assert measured == pytest.approx(expected_occupancy(q_mean, length, hashes), abs=0.006)
    assert fingerprint_collision_proxy(q_mean, length, hashes) == pytest.approx(
        (1 - math.exp(-hashes * q_mean / length)) ** hashes
    )


def test_tiny_length_has_one_bit_and_counts_each_distinct_token_once(golden_config):
    frame = pd.DataFrame({
        "record_id": ["A", "B"], "entity_id": ["E", "F"], "raw_item_description": ["x", None],
        "dosage": ["", None], "dosage_form": ["", ""], "pack_size": [None, ""],
    })
    enc = encoder_for_cell(golden_config, (1, 1), TEST_ROOT)
    tokens = cohort_tokens(frame, golden_config, "composite", enc)
    assert tokens == [{"_x", "x|", "||", "|_"}, {"_|", "||", "|_"}]
    assert not enc.grams("")
    np.testing.assert_array_equal(enc.encode_gram_sets(tokens), [[1], [1]])
    target = insertion_frequencies(tokens)
    bits = enc.encode_gram_sets(tokens)
    evaluator = FrequencyEvaluation.from_records(bits, target, target, enc)
    measures = evaluator.structural_metrics(bits, tokens, 1)
    assert measures["q_mean"] == 3.5
    assert measures["universe_size"] == 5
    assert measures["ambiguity_mean"] == measures["ambiguity_median"] == 5
    assert measures["entropy"] == 0
    assert evaluator.baseline == 1


def test_frequency_controls_pass_and_detect_failures():
    enc = BloomFilterEncoder(4096, 1, 2, TEST_ROOT, "_")
    tokens = [{gram} for count, gram in enumerate(("aa", "bb", "cc", "dd", "ee"), 1) for _ in range(count)]
    bits = enc.encode_gram_sets(tokens)
    ref = insertion_frequencies(tokens)
    control = Controls((4096, 1), 2.0, 20_000, 0.005)
    evaluator = FrequencyEvaluation.from_records(bits, ref, ref, enc)
    row = evaluator.control_row(ref, 4, "test", control)
    assert row["attack_success"] == 1
    assert row["random_baseline"] == pytest.approx(0.2)
    assert row["passed"]
    cfg = replace(load_collision_config(), controls=control)
    assert attack_control_passed(pd.DataFrame([row]), cfg)
    assert not attack_control_passed(pd.DataFrame([{**row, "attack_success": 0.2}]), cfg)
    assert not attack_control_passed(pd.DataFrame([{**row, "random_gap": 0.1}]), cfg)


def test_csv_schema_rejects_missing_duplicate_invalid_tau_and_invalid_dimensions():
    row = {"seed": 0, "noise": 0.15, "l": 1024, "k": 4, "tau": 0.9, "precision": 1.0,
           "recall": 1.0, "f1": 1.0, "fragmentation_rate": 1.0, "n_records": 2, "n_entities": 1,
           "n_pred_clusters": 1, "q_mean": 3.0, "q_median": 3.0, "universe_size": 3, "passed": True}
    validate_collision_csv("regression_gate", pd.DataFrame([row]))
    for broken in (pd.DataFrame([row, row]), pd.DataFrame([{**row, "tau": 0}]),
                   pd.DataFrame([{**row, "k": 1025}]), pd.DataFrame([{**row, "noise": -0.1}]),
                   pd.DataFrame([row]).drop(columns="f1"), pd.DataFrame([{**row, "passed": "True"}])):
        with pytest.raises(ValueError):
            validate_collision_csv("regression_gate", broken)


def test_csv_schema_allows_fractional_means_of_counts():
    columns = {f"{metric}_{stat}": None for metric in RUN_METRICS for stat in ("mean", "std")}
    group = dict(zip(GROUP_KEYS, ("description", 0.15, "bloom", 1024, 4), strict=True))
    row = {**group, **columns, "n_seeds": 5, "n_pred_clusters_mean": 54.6}
    validate_collision_csv("aggregated", pd.DataFrame([row]))


@pytest.mark.parametrize("name,value", [("baseline", [2, 3]), ("primary_noise", 1.1), ("tau_grid", {"start": 0, "stop": 1, "step": 1})])
def test_config_rejects_invalid_input(tmp_path, name, value):
    settings = yaml.safe_load((app_dir() / "configs" / "rq2_collision.yaml").read_text(encoding="utf-8"))
    settings[name] = value
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(settings), encoding="utf-8")
    with pytest.raises(ValueError):
        load_collision_config(path)


def _cohort_frame():
    return pd.DataFrame({
        "record_id": [f"R{i}" for i in range(36)],
        "entity_id": [f"E{i // 3}" for i in range(36)],
        "raw_item_description": ["", "a", "ab", "1a2", "123", "alpha"] * 6,
        "dosage": [""] * 36, "dosage_form": ["tablet"] * 36, "pack_size": ["30"] * 36,
    })


def test_paired_prepared_noise_matches_rq1_for_short_strings(tmp_path, monkeypatch, golden_config):
    base = _cohort_frame()
    cfg, seed, level = load_collision_config(), 0, 1.0
    noisy, log = inject_noise(base, level, golden_config.noise_fields, golden_config.typos_per_selected_record,
                             make_rng(seed, f"noise_{level}"))
    path = tmp_path / "noisy.csv"
    write_csv(noisy, path)
    monkeypatch.setattr(loader, "noisy_csv_path", lambda *_: path)
    partition = build_seed_partition(base, golden_config, cfg, seed)
    encoder = encoder_for_cell(golden_config, cfg.baseline, TEST_ROOT)
    cohorts = load_collision_cohorts(base, golden_config, cfg, seed, level, partition, encoder)
    expected = build_field_strings(noisy, "composite", golden_config, normalize=True)
    assert log["skipped_reason"].eq("short_text").sum() == 18
    for cohort in cohorts.values():
        ids = cohort.frame["record_id"]
        assert cohort.tokens == [encoder.grams(text) for text in expected.loc[ids]]


def test_entity_partitions_change_by_seed_and_pilot_uses_seed_zero_non_test(golden_config):
    cfg, frame = load_collision_config(), _cohort_frame()
    first = build_seed_partition(frame, golden_config, cfg, 0)
    assert first == build_seed_partition(frame, golden_config, cfg, 0)
    assert first != build_seed_partition(frame, golden_config, cfg, 1)
    validation, test, reference = map(set, first.values())
    assert not (validation & test or validation & reference or test & reference)
    assert validation | test | reference == set(frame["entity_id"])
    pilot = build_seed_partition(frame, golden_config, cfg, 0, pilot=True)
    assert set(pilot["validation"]) <= validation
    assert set(pilot["reference"]) <= reference


def test_deterministic_cell_files_and_cutoff_ignores_test(tmp_path, golden_config):
    cfg = load_collision_config()
    base = _cohort_frame()
    key, _ = derive_experiment_keys(TEST_ROOT, 0)
    partition = build_seed_partition(base, golden_config, cfg, 0)
    encoder = encoder_for_cell(golden_config, cfg.baseline, key)
    cohorts = load_collision_cohorts(base, golden_config, cfg, 0, 0.0, partition, encoder)

    def run(inputs, dirname):
        result = CollisionRuns()
        evaluate_bloom_cell(result, inputs, golden_config, cfg, seed=0, noise=0.0, variant="description",
                            pair=cfg.baseline, key=key, historical_tau=0.93)
        for name, rows in (("per_run", result.runs), ("tau_sweeps", result.sweeps), ("attack_results", result.attack)):
            write_collision_csv(name, pd.DataFrame(rows), tmp_path / dirname)
        return result

    first, second = run(cohorts, "first"), run(cohorts, "second")
    for path in (tmp_path / "first").iterdir():
        assert path.read_bytes() == (tmp_path / "second" / path.name).read_bytes()
    altered = dict(cohorts)
    test = altered["test"]
    altered["test"] = replace(test, frame=test.frame.assign(entity_id="E_changed"),
                              tokens=[{"zz"} for _ in test.tokens])
    third = run(altered, "third")
    assert first.validation == second.validation == third.validation
    assert first.sweeps == third.sweeps
    assert first.runs[0]["f1"] != third.runs[0]["f1"]


def test_key_source_is_private_and_domain_separated(monkeypatch, golden_config):
    cfg = load_collision_config()
    monkeypatch.delenv(cfg.key_env, raising=False)
    with pytest.raises(ValueError, match=cfg.key_env):
        load_experiment_root(cfg, golden_config)
    monkeypatch.setenv(cfg.key_env, TEST_ROOT.hex())
    root = load_experiment_root(cfg, golden_config)
    first, exact = derive_experiment_keys(root, 0)
    assert first != exact
    assert first != derive_experiment_keys(root, 1)[0]


def test_bootstrap_uses_zero_differences_and_unique_walsh_averages():
    baseline = pd.DataFrame({"seed": [0, 1, 2], "score": [0, 0, 0]})
    current = pd.DataFrame({"seed": [2, 1, 0], "score": [10, 1, 0]})
    differences = complete_seed_differences(baseline, current, "score")
    np.testing.assert_array_equal(differences, [0, 1, 10])
    result = paired_bootstrap_summary(differences, rng_seed=7, bootstrap_draws=5000)
    assert result["n_seeds"] == 3
    assert result["mean_difference"] == pytest.approx(11 / 3)
    assert result["hodges_lehmann"] == 3
    assert result["ci_low"] == 0
    assert result["ci_high"] == 10
    assert matched_rank_biserial(np.array([0, 1, 1, -8])) == 0
    assert matched_rank_biserial(np.array([0, 1, -8])) == pytest.approx(-1 / 3)


def test_recommendation_applies_validation_f1_budget_and_reports_near_ties():
    cfg = load_collision_config()
    rows = []
    for seed, candidate in enumerate((0.08, 0.10, 0.09, 0.10, 0.08)):
        for l, k, success, f1 in ((1024, 4, 0.1, 0.9), (512, 4, candidate, 0.89),
                                   (1024, 2, 0.09, 0.91), (256, 2, 0.01, 0.80)):
            rows.append({"l": l, "k": k, "seed": seed, "attack_success": success, "f1": f1})
    selected = select_collision_config(pd.DataFrame(rows), cfg)
    assert selected.recommended == (1024, 2)
    assert selected.extreme == (256, 2)
    assert (512, 4) in selected.near_ties
