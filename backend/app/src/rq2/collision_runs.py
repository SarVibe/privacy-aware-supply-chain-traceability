"""Run paired collision cells and export aggregate-only frequency diagnostics."""

from dataclasses import dataclass, field

import pandas as pd

from src.common.config import Config
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.rq2.collision_cohorts import Cohort, encoder_for_cell
from src.rq2.collision_config import CollisionConfig
from src.rq2.collision_linkage import prepare_collision_scores
from src.rq2.collision_privacy import FrequencyEvaluation, insertion_frequencies
from src.rq2.collision_schema import RUN_METRICS
from src.rq2.collision_utility import Separation, score_bloom_test, score_exact_test, validation_cutoff


@dataclass
class CollisionRuns:
    runs: list[dict] = field(default_factory=list)
    attack: list[dict] = field(default_factory=list)
    sweeps: list[dict] = field(default_factory=list)
    validation: list[dict] = field(default_factory=list)
    histograms: dict[tuple[int, int], list[Separation]] = field(default_factory=dict)


def measure_control(
    cohorts: dict[str, Cohort], encoder: BloomFilterEncoder, cfg: CollisionConfig, seed: int
) -> list[dict]:
    reference = insertion_frequencies(cohorts["reference"].tokens)
    rows = []
    for name in ("validation", "test"):
        cohort = cohorts[name]
        bits = encoder.encode_gram_sets(cohort.tokens)
        evaluator = FrequencyEvaluation.from_records(bits, insertion_frequencies(cohort.tokens), reference, encoder)
        rows.append(evaluator.control_row(reference, seed, name, cfg.controls))
    return rows


def _privacy_metrics(identity, split, cohort, encoder, reference, bits, seed, hashes):
    truth = insertion_frequencies(cohort.tokens)
    evaluator = FrequencyEvaluation.from_records(bits, truth, reference, encoder)
    rows = [
        {"attack": attack, **evaluator.alignment_metrics(population, seed, f"rq2:{split}:{attack}")}
        for attack, population in (("reference", reference), ("own_frequencies", truth))
    ]
    return (
        [{**identity, "split": split, **row} for row in rows],
        evaluator.structural_metrics(bits, cohort.tokens, hashes),
    )


def evaluate_bloom_cell(
    results: CollisionRuns, cohorts: dict[str, Cohort], rq1: Config, cfg: CollisionConfig,
    *, seed: int, noise: float, variant: str, pair: tuple[int, int], key: bytes, historical_tau: float | None,
    collect_histograms: bool = False,
) -> None:
    l, k = pair
    identity = {"variant": variant, "noise": noise, "seed": seed, "method": "bloom", "l": l, "k": k}
    encoder = encoder_for_cell(rq1, pair, key)
    bits = {name: encoder.encode_gram_sets(cohort.tokens) for name, cohort in cohorts.items()}
    reference = insertion_frequencies(cohorts["reference"].tokens)
    validation = cohorts["validation"]
    validation_scores = prepare_collision_scores(validation.frame, bits["validation"], rq1)
    tau, sweep = validation_cutoff(validation, validation_scores, cfg.taus, rq1)
    validation_attack, _ = _privacy_metrics(identity, "validation", validation, encoder, reference,
                                           bits["validation"], seed, k)
    chosen = sweep.loc[sweep["tau"] == tau].iloc[0]
    results.validation.append({**identity, "tau": tau, "f1": float(chosen["f1"]),
                               "attack_success": validation_attack[0]["attack_success"]})
    results.sweeps.extend({**identity, **row} for row in sweep.to_dict("records"))
    results.attack.extend(validation_attack)
    if "test" not in cohorts:
        return

    test = cohorts["test"]
    test_scores = prepare_collision_scores(test.frame, bits["test"], rq1)
    utility, separation = score_bloom_test(test, test_scores, rq1, tau, cfg.analysis.histogram_bins, historical_tau)
    attack, structural = _privacy_metrics(identity, "test", test, encoder, reference, bits["test"], seed, k)
    results.attack.extend(attack)
    if collect_histograms:
        results.histograms.setdefault(pair, []).append(separation)
    results.runs.append({**identity, **utility, **structural, "tau": tau, "pr_auc": separation.pr_auc,
                         "dice_overlap": separation.dice_overlap,
                         **{name: attack[0][name] for name in ("attack_success", "random_baseline", "lift", "used_bits")}})


def evaluate_exact_baseline(
    results: CollisionRuns, cohort: Cohort, rq1: Config, cfg: CollisionConfig, *, seed: int, key: bytes,
) -> None:
    utility, separation = score_exact_test(cohort, rq1, cfg.field_set, key, cfg.analysis.histogram_bins)
    metrics = dict.fromkeys(RUN_METRICS)
    metrics.update(utility, pr_auc=separation.pr_auc, dice_overlap=separation.dice_overlap)
    results.runs.append({"variant": "description", "noise": cfg.primary_noise, "seed": seed, "method": "exact",
                         "l": 0, "k": 0, **metrics})


def attack_control_passed(frame: pd.DataFrame, cfg: CollisionConfig) -> bool:
    pooled = frame.groupby("split")[["attack_success", "random_baseline"]].mean()
    return bool((frame["random_gap"] <= cfg.controls.max_random_gap).all()
                and (pooled["attack_success"] >= pooled["random_baseline"] * cfg.controls.min_lift).all())
