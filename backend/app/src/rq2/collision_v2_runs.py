"""Execute v2 cells within the frozen validation and test protocol."""

from dataclasses import dataclass, field
from itertools import combinations

import pandas as pd

from src.common.linking.threshold import select_single_tau
from src.rq2.collision_cohorts import encoder_for_cell
from src.rq2.collision_linkage import prepare_collision_scores, score_collision_clusters
from src.rq2.collision_privacy import FrequencyEvaluation, insertion_frequencies
from src.rq2.collision_utility import Separation, score_bloom_test, score_exact_test, validation_cutoff
from src.rq2.collision_v2_artifacts import ACCURACY, UTILITY
from src.rq2.collision_v2_metrics import diagnose_edges, known_key_metrics, matched_control, matched_frequency, v2_occupancy


@dataclass
class V2Runs:
    per_run: list[dict] = field(default_factory=list)
    exact_baseline: list[dict] = field(default_factory=list)
    e1: list[dict] = field(default_factory=list)
    e2: list[dict] = field(default_factory=list)
    tau_sweeps: list[dict] = field(default_factory=list)
    tau_sensitivity: list[dict] = field(default_factory=list)
    validation: list[dict] = field(default_factory=list)
    histograms: dict[tuple[int, int], list[Separation]] = field(default_factory=dict)


def control_v2_cohorts(cohorts, encoder, seed, cfg) -> list[dict]:
    reference = insertion_frequencies(cohorts["reference"].tokens)
    rows = []
    for name in ("validation", "test"):
        tokens = cohorts[name].tokens
        bits = encoder.encode_gram_sets(tokens)
        evaluator = FrequencyEvaluation.from_records(bits, insertion_frequencies(tokens), reference, encoder)
        rows.append(matched_control(evaluator, reference, seed, name, cfg.controls))
    return rows


def v2_control_passed(controls: pd.DataFrame, settings) -> bool:
    mean = controls.groupby("split")[["hit", "null_matched"]].mean()
    return bool((mean["null_matched"] > 0).all()
                and (mean["hit"] >= settings.min_matched_lift * mean["null_matched"]).all()
                and (controls["random_gap"] <= settings.max_random_gap).all())


def _privacy_row(results, identity, name, cohort, bits, reference, encoder):
    frequencies = insertion_frequencies(cohort.tokens)
    evaluator = FrequencyEvaluation.from_records(bits, frequencies, reference, encoder)
    e1 = {}
    for frequency_source, candidates, old_name in (("reference", reference, "reference"),
                                                    ("own_frequencies", frequencies, "own_frequencies")):
        scores = matched_frequency(evaluator, candidates, identity["seed"], f"rq2:{name}:{old_name}")
        results.e1.append({**identity, "split": name, "frequency_source": frequency_source, **scores})
        if frequency_source == "reference":
            e1 = scores
    e2 = known_key_metrics(bits, cohort.tokens, evaluator) | v2_occupancy(bits, cohort.tokens, evaluator, identity["k"])
    results.e2.append({**identity, "split": name, **e2})
    return e1, e2


def _threshold_row(cohort, prepared, tau, rq1):
    truth = cohort.frame.set_index(rq1.columns.record_id)[rq1.columns.entity_id]
    cluster = score_collision_clusters(cohort.frame, prepared, tau, rq1)
    return ({name: cluster[name] for name in ACCURACY} | diagnose_edges(prepared, truth, tau))


def _sensitivity(results, identity, cohorts, prepared, cfg, rq1):
    sweep = [
        {"tau": tau, **_threshold_row(cohorts["validation"], prepared["validation"], tau, rq1)}
        for tau in cfg.sensitivity_taus
    ]
    best = select_single_tau(pd.DataFrame(sweep))
    results.tau_sensitivity.extend({**identity, "split": "validation", "selected": row["tau"] == best, **row}
                                   for row in sweep)
    test = _threshold_row(cohorts["test"], prepared["test"], best, rq1)
    results.tau_sensitivity.append({**identity, "split": "test", "tau": best, "selected": True, **test})


def evaluate_v2_cell(
    results: V2Runs, cohorts, rq1, cfg, *, seed: int, noise: float, variant: str,
    pair: tuple[int, int], key: bytes, histograms: bool = False,
) -> None:
    identity = dict(variant=variant, noise=noise, seed=seed, l=pair[0], k=pair[1])
    encoder = encoder_for_cell(rq1, pair, key)
    bits = {name: encoder.encode_gram_sets(cohort.tokens) for name, cohort in cohorts.items()}
    reference = insertion_frequencies(cohorts["reference"].tokens)
    prepared = {"validation": prepare_collision_scores(cohorts["validation"].frame, bits["validation"], rq1)}
    tau, scores = validation_cutoff(cohorts["validation"], prepared["validation"], cfg.taus, rq1)
    results.tau_sweeps.extend({**identity, **row} for row in scores.loc[:, ["tau", *ACCURACY]].to_dict("records"))
    _, validation_e2 = _privacy_row(results, identity, "validation", cohorts["validation"], bits["validation"], reference, encoder)
    results.validation.append({**identity, "tau": tau, "f1": float(scores.loc[scores["tau"].eq(tau), "f1"].item()),
                               "e2_precision_mean": validation_e2["e2_precision_mean"]})
    test = cohorts["test"]
    prepared["test"] = prepare_collision_scores(test.frame, bits["test"], rq1)
    utility, separation = score_bloom_test(test, prepared["test"], rq1, tau, cfg.analysis.histogram_bins, None)
    truth = test.frame.set_index(rq1.columns.record_id)[rq1.columns.entity_id]
    diagnostics = diagnose_edges(prepared["test"], truth, tau)
    test_e1, test_e2 = _privacy_row(results, identity, "test", test, bits["test"], reference, encoder)
    utility = {**utility, "pr_auc": separation.pr_auc, "dice_overlap": separation.dice_overlap}
    results.per_run.append({**identity, "tau": tau, **{name: utility[name] for name in UTILITY},
                            **diagnostics, **test_e1, **test_e2})
    if tau == cfg.taus[-1]:
        _sensitivity(results, identity, cohorts, prepared, cfg, rq1)
    if histograms:
        results.histograms.setdefault(pair, []).append(separation)


def v2_exact_row(cohort, rq1, cfg, seed, key):
    utility, separation = score_exact_test(cohort, rq1, cfg.field_set, key, cfg.analysis.histogram_bins)
    metrics = utility | {"pr_auc": separation.pr_auc, "dice_overlap": separation.dice_overlap}
    return {"variant": "description", "noise": cfg.primary_noise, "seed": seed,
            **{name: metrics[name] for name in UTILITY}}


def entity_overlap(partitions, pilot_seed, pilot):
    def row(scope, a, b, split_a, split_b, ids_a, ids_b):
        left, right = set(ids_a), set(ids_b)
        return dict(scope=scope, seed_a=a, seed_b=b, split_a=split_a, split_b=split_b, entities_a=len(left),
                    entities_b=len(right), entities_shared=len(left & right), jaccard=len(left & right) / len(left | right))

    rows = [row("cross_seed", a, b, "test", "test", partitions[a]["test"], partitions[b]["test"])
            for a, b in combinations(partitions, 2)]
    pilot_groups = {**pilot, "all": sum(pilot.values(), [])}
    rows.extend(row("pilot_to_test", pilot_seed, seed, name, "test", ids, split["test"])
                for seed, split in partitions.items() for name, ids in pilot_groups.items())
    return rows
