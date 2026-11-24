"""Measure direct errors, transitive amplification, field overlap, and saturation."""

from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.rq1.diagnostic_inputs import OUTPUT_ROOT, diagnostic_cases
from src.common.config import load_config
from src.common.encoding.bloom_filter import BloomFilterEncoder, fill_ratio
from src.common.evaluation.metrics import evaluate_clusters, pairwise_prf
from src.common.experiment.io import write_csv
from src.common.linking.clustering import labels_from_pairs
from src.common.preprocessing.field_builder import build_field_strings
from src.common.preprocessing.normalizer import normalize_series
from src.common.similarity.dice import dice_matrix

DEFAULT_OUTPUT = OUTPUT_ROOT / "rq1_overmerge"
QUANTILES = (1, 5, 25, 50, 75, 95, 99)
PAIR_GROUPS = ("true_match", "all_nonmatch", "same_structure_different_description")
BINS = np.linspace(0, 1, 31)


def diagnostic_quantiles(values):
    quantiles = np.percentile(values, QUANTILES) if len(values) else [np.nan] * len(QUANTILES)
    return {"n": len(values), **{f"p{q:02d}": value for q, value in zip(QUANTILES, quantiles, strict=True)}}


def direct_pair_scores(true, predicted, *, empty_score):
    counts = int(np.count_nonzero(true & predicted)), int(np.count_nonzero(predicted)), int(np.count_nonzero(true))
    p, r, f1 = pairwise_prf(*counts, empty_score=empty_score)
    return {"precision": p, "recall": r, "f1": f1, "true_positives": counts[0], "predicted_pairs": counts[1]}


def component_profile(truth, labels):
    records = pd.DataFrame({"cluster": np.asarray(labels), "entity": np.asarray(truth)})
    sizes = records.groupby("cluster", sort=True).entity.agg(size="size", true_entities="nunique")
    sizes = sizes.sort_values("size", ascending=False, kind="stable")
    sizes["predicted_pairs"] = sizes["size"] * (sizes["size"] - 1) // 2
    pair_count = int(sizes["predicted_pairs"].sum())
    return {
        "clusters": len(sizes), "largest_component": int(sizes["size"].iloc[0]),
        "largest_component_true_entities": int(sizes["true_entities"].iloc[0]),
        "predicted_pairs": pair_count,
        "top_3_pair_share": float(sizes["predicted_pairs"].head(3).sum() / pair_count) if pair_count else 0.0,
    }, sizes


def plot_distributions(histograms, datasets, noise_levels, path):
    centers = (BINS[1:] + BINS[:-1]) / 2
    colors = ("#0072B2", "#555555", "#D55E00")
    for dataset in datasets:
        figure, axes = plt.subplots(2, len(noise_levels), figsize=(13, 5), sharex=True, layout="constrained")
        for index, field in enumerate(("composite", "description")):
            for column, noise in enumerate(noise_levels):
                axis = axes[index, column]
                for label, color in zip(PAIR_GROUPS, colors, strict=True):
                    counts = histograms[(dataset, field, noise, label)]
                    if counts.sum():
                        axis.step(centers, counts / counts.sum(), where="mid", label=label.replace("_", " "), color=color)
                axis.set_title(f"{field}, {noise:.0%} noise")
                axis.set_xlim(0, 1)
                if column == 0:
                    axis.set_ylabel("Fraction per bin")
                if index == 1:
                    axis.set_xlabel("Dice")
        handles, legend = axes[0, 0].get_legend_handles_labels()
        figure.legend(handles, legend, loc="outside lower center", ncol=3, frameon=False)
        figure.savefig(path / f"dice_{dataset}.png", dpi=150)
        plt.close(figure)


def main():
    cfg = load_config("rq1_diagnostics")
    bloom = cfg.bloom
    encoder = BloomFilterEncoder(bloom.l, bloom.k, bloom.q, bytes.fromhex(bloom.hmac_key), bloom.pad_char)
    rid, eid = cfg.columns.record_id, cfg.columns.entity_id
    threshold_rows, sizes_rows, large_rows, quantile_rows, encoding_rows, shared_rows = [], [], [], [], [], []
    histograms = defaultdict(lambda: np.zeros(len(BINS) - 1, dtype=np.int64))
    datasets = set()
    for case in diagnostic_cases(cfg):
        datasets.add(case.dataset)
        frame = case.test
        clean = case.clean.set_index(rid).loc[frame[rid]].reset_index()
        truth = frame.set_index(rid)[eid]
        entities = truth.to_numpy()
        pair = np.triu_indices(len(frame), 1)
        true = entities[pair[0]] == entities[pair[1]]
        structure = frame[list(cfg.columns.text[1:])].apply(normalize_series).to_numpy()
        descriptions = normalize_series(frame[cfg.columns.description]).to_numpy()
        shared = (~true) & (structure[pair[0]] == structure[pair[1]]).all(axis=1)
        shared_different = shared & (descriptions[pair[0]] != descriptions[pair[1]])
        distinct_pairs = {
            tuple(sorted((a, b))) for a, b in zip(entities[pair[0][shared]], entities[pair[1][shared]], strict=True)
        }
        total_entities = truth.nunique()
        context = {"dataset": case.dataset, "seed": case.seed, "noise": case.noise, "n_records": len(frame)}
        shared_rows.append({
            **context, "nonmatch_pairs": int((~true).sum()), "shared_structure_pairs": int(shared.sum()),
            "shared_structure_share": float(shared.sum() / (~true).sum()),
            "different_description_pairs": int(shared_different.sum()),
            "distinct_entity_pairs_sharing_structure": len(distinct_pairs),
            "distinct_entity_pairs": total_entities * (total_entities - 1) // 2,
        })
        grams_by_field = {}
        for field_set in ("description", "composite"):
            texts = build_field_strings(frame, field_set, cfg, normalize=True)
            bits = encoder.encode_many(texts)
            unique_grams = [encoder.grams(text) for text in texts]
            grams_by_field[field_set] = unique_grams
            q_counts = np.array([len(grams) for grams in unique_grams])
            distributions = {"q_count": q_counts, "actual_fill": fill_ratio(bits),
                             "expected_fill": -np.expm1(-bloom.k * q_counts / bloom.l)}
            if field_set == "composite":
                new_grams = np.array([
                    len(composite - name) for composite, name in zip(
                        unique_grams, grams_by_field["description"], strict=True
                    )
                ])
                distributions["non_description_gram_share"] = np.divide(
                    new_grams, q_counts, out=np.zeros(len(frame)), where=q_counts > 0
                )
            for metric, values in distributions.items():
                encoding_rows.append({
                    **context, "field_set": field_set, "metric": metric,
                    "mean": float(values.mean()), **diagnostic_quantiles(values),
                })
            scores = dice_matrix(bits, bits)[pair]
            for label, mask in zip(PAIR_GROUPS, (true, ~true, shared_different), strict=True):
                values = scores[mask]
                quantile_rows.append({
                    **context, "field_set": field_set, "pair_group": label, **diagnostic_quantiles(values),
                })
                histograms[(case.dataset, field_set, case.noise, label)] += np.histogram(values, bins=BINS)[0]
            if field_set != "composite":
                continue
            clean_texts = build_field_strings(clean, field_set, cfg, normalize=True)
            cross_scores = dice_matrix(encoder.encode_many(clean_texts), bits)
            cross_mask = ~np.eye(len(frame), dtype=bool)
            cross_truth = (entities[:, None] == entities[None, :])[cross_mask]
            for tau in cfg.diagnostics.fixed_taus:
                labels = labels_from_pairs(len(frame), *pair, scores, tau)
                cluster_metrics = evaluate_clusters(truth, pd.Series(labels, index=truth.index))
                stats, sizes = component_profile(truth, labels)
                within = direct_pair_scores(true, scores >= tau, empty_score=1)
                cross = direct_pair_scores(cross_truth, cross_scores[cross_mask] >= tau, empty_score=0)
                dimensions = {**context, "tau": tau}
                threshold_rows.append({
                    **dimensions, **stats, **{f"cluster_{key}": value for key, value in cluster_metrics.items()},
                    **{f"direct_{key}": value for key, value in within.items()},
                    **{f"cross_party_{key}": value for key, value in cross.items()},
                    "added_by_closure": stats["predicted_pairs"] - within["predicted_pairs"],
                    "added_false_pairs": int(np.count_nonzero(
                        (labels[pair[0]] == labels[pair[1]]) & (scores < tau) & (~true)
                    )),
                })
                for size, count in sizes["size"].value_counts().sort_index().items():
                    sizes_rows.append({**dimensions, "component_size": size, "count": count})
                for rank, component in enumerate(sizes.head(3).itertuples(), 1):
                    large_rows.append({
                        **dimensions, "rank": rank, "component_id": component.Index, "size": component.size,
                        "true_entities": component.true_entities, "predicted_pairs": component.predicted_pairs,
                    })
    for filename, rows in (
        ("threshold_metrics.csv", threshold_rows), ("component_sizes.csv", sizes_rows),
        ("large_components.csv", large_rows), ("dice_quantiles.csv", quantile_rows),
        ("encoding_distributions.csv", encoding_rows), ("structured_sharing.csv", shared_rows),
    ):
        write_csv(pd.DataFrame(rows), DEFAULT_OUTPUT / filename)
    plot_distributions(histograms, sorted(datasets), cfg.noise_levels, DEFAULT_OUTPUT)
    print(f"Saved {len(threshold_rows)} threshold evaluations to {DEFAULT_OUTPUT}")


if __name__ == "__main__":
    main()
