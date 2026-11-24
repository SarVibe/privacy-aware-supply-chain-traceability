"""Build paired effects, Pareto views, figures and the report-ready tables."""

import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.common.evaluation.aggregation import aggregate_runs, complete_seed_differences, paired_bootstrap_summary
from src.common.reporting.tables import format_mean_std
from src.rq2.collision_config import CollisionConfig
from src.rq2.collision_runs import CollisionRuns
from src.rq2.collision_schema import COMPARISON, GROUP_KEYS, RUN_METRICS, write_collision_csv
from src.rq2.collision_selection import Selection


def _cell(rows, pair):
    return rows.loc[(rows["l"] == pair[0]) & (rows["k"] == pair[1])]


def _pareto(primary, selection):
    points = primary[["l", "k", "attack_success_mean", "f1_mean"]].rename(
        columns={"attack_success_mean": "attack_success", "f1_mean": "f1"}
    ).merge(selection.table, on=["l", "k"], validate="one_to_one")
    points["pareto"] = [
        not ((points["attack_success"] <= row.attack_success) & (points["f1"] >= row.f1)
             & ((points["attack_success"] < row.attack_success) | (points["f1"] > row.f1))).any()
        for row in points.itertuples(index=False)
    ]
    return points


def _paired_effects(runs, cfg):
    baseline = _cell(runs, cfg.baseline)
    rows = []
    for (l, k), cell in runs.groupby(["l", "k"]):
        if (l, k) == cfg.baseline:
            continue
        for metric in ("attack_success", "f1", "pr_auc", "fill", "ambiguity_mean"):
            differences = complete_seed_differences(baseline, cell, metric)
            effect = paired_bootstrap_summary(differences, rng_seed=cfg.analysis.seed,
                                              bootstrap_draws=cfg.analysis.bootstrap_draws)
            rows.append({"l": l, "k": k, "metric": metric, **effect})
    return pd.DataFrame(rows)


def _trends(runs):
    rows = []

    def _append_trends(hypothesis, scope, group, predictor, outcomes):
        for outcome in outcomes:
            data = group[[predictor, outcome]].dropna()
            rho = (float(spearmanr(data[predictor], data[outcome]).statistic)
                   if (data.nunique() > 1).all() else np.nan)
            rows.append({"hypothesis": hypothesis, "scope": scope, "predictor": predictor,
                         "outcome": outcome, "n_pairs": len(data), "spearman_rho": rho})

    for k, group in runs.groupby("k"):
        _append_trends("H1", f"k={k}", group, "l", ("attack_success", "ambiguity_mean", "f1", "pr_auc", "dice_overlap"))
    for l, group in runs.groupby("l"):
        _append_trends("H2", f"l={l}", group, "k", ("fill",))
    for label, group in (("fill<0.5", runs.loc[runs["fill"] < 0.5]), ("fill>0.5", runs.loc[runs["fill"] > 0.5])):
        _append_trends("H2", label, group, "fill", ("entropy", "f1"))
    return pd.DataFrame(rows)


def _cross_check(aggregated, cfg, selection):
    pairs = {cfg.baseline, selection.recommended, selection.extreme}
    masks = [(l, k) in pairs for l, k in zip(aggregated["l"], aggregated["k"], strict=True)]
    cols = [f"{metric}_{stat}" for metric in COMPARISON for stat in ("mean", "std")]
    cells = aggregated.loc[masks, ["variant", "noise", "l", "k", "n_seeds", *cols]].copy()
    baseline = _cell(cells, cfg.baseline).set_index(["variant", "noise"])
    for metric in COMPARISON:
        baseline_means = [
            baseline.loc[(row.variant, row.noise), f"{metric}_mean"] for row in cells.itertuples(index=False)
        ]
        cells[f"{metric}_delta_vs_baseline"] = cells[f"{metric}_mean"] - baseline_means
    return cells.sort_values(["variant", "noise", "l", "k"], ascending=[True, True, False, True])


def _plots(directory, primary, pareto, selection, cfg, histograms):
    directory.mkdir()
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(pareto["attack_success"], pareto["f1"], color="#2b6777", label="Bloom grid")
    front = pareto.loc[pareto["pareto"]].sort_values("attack_success")
    ax.plot(front["attack_success"], front["f1"], color="#2b6777", alpha=0.55)
    for pair, label, marker in ((cfg.baseline, "Baseline 2", "s"), (selection.recommended, "Recommended", "*")):
        row = _cell(pareto, pair).iloc[0]
        ax.scatter(row["attack_success"], row["f1"], marker=marker, s=135, label=label)
    ax.set(xlabel="Held-out frequency-alignment success", ylabel="Held-out pairwise F1",
           title="Collision tuning trade-off")
    ax.legend()
    fig.tight_layout()
    fig.savefig(directory / "privacy_vs_f1.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    for ax, metric, title in zip(axes, ("attack_success", "f1", "fill"), ("Attack success", "Pairwise F1", "Fill ratio")):
        grid = primary.pivot(index="l", columns="k", values=f"{metric}_mean").sort_index(ascending=False)
        values = grid.to_numpy()
        heatmap = ax.imshow(values, cmap="viridis", vmin=0, vmax=1, aspect="auto")
        ax.set(xticks=range(len(grid.columns)), xticklabels=grid.columns, yticks=range(len(grid.index)),
               yticklabels=grid.index, xlabel="Hash count k", ylabel="Filter length l", title=title)
        for (i, j), value in np.ndenumerate(values):
            ax.text(j, i, f"{value:.3f}", ha="center", va="center", color="black" if value > 0.6 else "white")
        fig.colorbar(heatmap, ax=ax, shrink=0.7)
    fig.savefig(directory / "grid_heatmaps.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True, layout="constrained")
    bins = np.linspace(0, 1, cfg.analysis.histogram_bins + 1)
    for ax, (label, pair) in zip(axes, (("Baseline 2", cfg.baseline), ("Recommended", selection.recommended),
                                       ("Lowest validation attack success", selection.extreme))):
        for metric, title, color in (("match", "Match", "#197278"), ("nonmatch", "Non-match", "#bb4d38")):
            counts = np.sum([getattr(item, metric) for item in histograms[pair]], axis=0)
            if counts.sum():
                ax.stairs(counts / counts.sum(), bins, label=title, color=color, linewidth=1.8)
        ax.set(xlabel="Raw Dice", title=f"{label}\nl={pair[0]}, k={pair[1]}", xlim=(0, 1))
    axes[0].set_ylabel("Pair fraction per bin")
    axes[0].legend()
    fig.savefig(directory / "dice_distributions.png", dpi=160)
    plt.close(fig)


def _markdown(primary, exact, pareto, cross, effects, trends, controls, gate, cfg, selection):
    baseline = _cell(pareto, cfg.baseline).iloc[0]
    winner = _cell(pareto, selection.recommended).iloc[0]
    attack_reduction = ((baseline["attack_success"] - winner["attack_success"]) / baseline["attack_success"]
                        if baseline["attack_success"] else None)
    h3 = cfg.analysis.h3_relative_reduction
    h3_pass = primary.loc[
        (primary["attack_success_mean"] <= baseline["attack_success"] * (1 - h3))
        & (primary["f1_mean"] >= baseline["f1"] - cfg.analysis.f1_budget)
    ] if baseline["attack_success"] > 0 else primary.iloc[:0]
    roles = ", ".join(f"({l}, {k})" for l, k in selection.near_ties) or "None"
    table = pd.concat([primary, exact], ignore_index=True)
    score_names = ("precision", "recall", "f1", "pr_auc", "dice_overlap", "attack_success", "random_baseline", "fill")
    display = table[["method", "l", "k"]].copy()
    for metric in score_names:
        display[metric] = [format_mean_std(mean, std) for mean, std in
                           zip(table[f"{metric}_mean"], table[f"{metric}_std"], strict=True)]
    control_summary = controls.groupby("split", as_index=False).agg(
        positive_success=("attack_success", "mean"), random_baseline=("random_baseline", "mean"),
        random_alignment=("random_control_mean", "mean"), max_random_gap=("random_gap", "max"),
    )
    control_summary["positive_lift"] = control_summary["positive_success"] / control_summary["random_baseline"]
    effect_rows = _cell(effects, selection.recommended)
    robustness_view = cross[["variant", "noise", "l", "k", "f1_mean", "f1_std", "f1_delta_vs_baseline",
                             "attack_success_mean", "attack_success_std", "attack_success_delta_vs_baseline"]]
    setting = f"({selection.recommended[0]}, {selection.recommended[1]})"
    reduction_label = f"{attack_reduction:.1%}" if attack_reduction is not None else "undefined"
    return "\n".join([
        "# RQ2 collision tuning", "",
        f"The empirical benchmark ran {len(primary)} Bloom configurations on {len(cfg.seeds)} paired seeds at "
        f"{cfg.primary_noise:.0%} description noise. The frozen RQ1 replay matched all seven fields on {len(gate)} seeds "
        "with all four frozen artifact hashes unchanged.", "",
        "## Validation selection and held-out results", "",
        f"Validation selected (l, k) = {setting} with F1 {winner['validation_f1']:.4f} and attack success "
        f"{winner['validation_attack_success']:.4f}. The validation F1 floor was {selection.minimum_f1:.4f}. "
        f"The lowest validation attack-success cell across the unfiltered grid was {selection.extreme}. "
        f"Eligible near-ties by the paired validation leakage interval were {roles}.", "",
        f"Held-out F1 was {winner['f1']:.4f} for the recommendation and {baseline['f1']:.4f} for Baseline 2. "
        f"Attack success was {winner['attack_success']:.4f} and {baseline['attack_success']:.4f}, respectively "
        f"(relative reduction {reduction_label}). Historical RQ1 cutoffs appear only as a secondary Baseline 2 comparison.", "",
        display.to_markdown(index=False), "",
        "## Frequency controls", "", control_summary.to_markdown(index=False, floatfmt=".6f"), "",
        "The positive control uses the common encoder at l=4096 and k=1 with no bit perturbation. The gate requires "
        f"positive-control lift of at least {cfg.controls.min_lift:g} in each split pooled across seeds, and "
        f"random-alignment absolute error at most {cfg.controls.max_random_gap:g} in every seed and split.", "",
        "## Hypotheses and paired effects", "",
        f"H3 was frozen at a relative attack-success reduction of {h3:.0%} with an F1 loss budget of "
        f"{cfg.analysis.f1_budget:.2f}. {len(h3_pass)} held-out grid cells met both descriptive criteria. "
        "The number of qualifying cells does not influence the validation recommendation.", "",
        "H1 and H2 trends use Spearman correlations over pooled seed-specific observations within each fixed setting. "
        "The reported coefficients and seed bootstrap intervals are descriptive.", "",
        trends.to_markdown(index=False, floatfmt=".3f"), "",
        "Paired differences are recommendation minus Baseline 2 on the same seeds. Intervals are 95% "
        "paired percentile bootstrap intervals. Equal outcomes are retained in resampling.", "",
        (effect_rows.to_markdown(index=False, floatfmt=".4f") if not effect_rows.empty else
         "The recommendation coincided with Baseline 2, so their paired difference was zero."), "",
        "## Noise cross-check", "", robustness_view.to_markdown(index=False, floatfmt=".4f"), "",
        "## Measurement definitions", "",
        "- The adversary knows the Bloom scheme and has its own plaintext reference corpus. The evaluator holds the key. "
        "The main reference entities are disjoint from both target partitions. The database-frequency variant uses target "
        "frequencies as secondary evidence. The exported results contain only aggregate attack measurements.",
        "- The insertion universe for each target is the union of that target's literal padded separator-delimited bigrams "
        "and the reference bigrams. Q counts distinct inserted bigrams per record. Rank quantiles map each used bit to "
        "one reference token. The evaluator tests membership in the bit's token set. Uniform random guesses draw from "
        "the evaluator universe. Ambiguity includes every bit position and counts distinct tokens once per bit.",
        "- The collision proxy uses the measured target mean Q. Multiplying the proxy by universe size gives an "
        "approximate whole-filter false-candidate count. Per-bit ambiguity comes from the actual keyed bit memberships. "
        "Occupancy entropy is the binary entropy of the mean fill ratio.",
        "- PR-AUC uses average precision on every unordered within-cohort pair considered by RQ1's linker. Dice overlap "
        "sums the smaller class-normalized frequency in each equal-width bin. The exact baseline uses binary equality scores.",
        "- Secondary cross-party numbers use two seeded synthetic parties formed by a balanced partition of stable record IDs "
        "within each split. Only unordered pairs with one record in each party are eligible. They use the same cluster "
        "labels and entity IDs as the primary metric and do not measure real organization effects.", "",
        "## Limitations", "",
        "- These are empirical measurements for one frequency-alignment attack, one threat model, one shipment dataset "
        "and one composite representation. RQ3 addresses formal differential privacy.",
        "- The default typo generator changes only descriptions. Dosage, dosage form and pack size remain available to "
        "the encoder and also contribute to ground truth. The optional all-fields row uses separately prepared artifacts.",
        "- Both the collision proxy and occupancy depend on composite Q. Saturated filters amplify accidental membership "
        "and ties, and can increase raw attack success even as ambiguity grows. A known-key analysis here is analytical only.",
        "- Reference and target entities come from the same prepared shipment population and differ in their realized "
        "distributions. A single pilot fold and five partially overlapping resamples limit uncertainty interpretation. "
        "Control lift and near-ties can vary with the experimental keys and splits.", "",
    ])


def write_collision_report(
    results: CollisionRuns, selection: Selection, gate: pd.DataFrame, controls: pd.DataFrame,
    cfg: CollisionConfig, destination: Path, fingerprints: dict, partitions: dict, extended: bool,
) -> None:
    runs = pd.DataFrame(results.runs)
    aggregated = aggregate_runs(runs, GROUP_KEYS, RUN_METRICS)
    primary_mask = aggregated["noise"].eq(cfg.primary_noise) & aggregated["variant"].eq("description")
    primary = aggregated.loc[primary_mask & aggregated["method"].eq("bloom")]
    exact = aggregated.loc[primary_mask & aggregated["method"].eq("exact")]
    primary_runs = runs.loc[runs["noise"].eq(cfg.primary_noise) & runs["variant"].eq("description")
                            & runs["method"].eq("bloom")]
    pareto = _pareto(primary, selection)
    effects = _paired_effects(primary_runs, cfg)
    trends = _trends(primary_runs)
    cross = _cross_check(aggregated, cfg, selection)
    with TemporaryDirectory(dir=destination) as temporary:
        stage = Path(temporary)
        frames = {
            "per_run": runs, "aggregated": aggregated, "attack_results": pd.DataFrame(results.attack),
            "controls": controls, "tau_sweeps": pd.DataFrame(results.sweeps), "pareto": pareto,
            "cross_check": cross, "paired_effects": effects, "trends": trends,
        }
        for name, frame in frames.items():
            write_collision_csv(name, frame, stage)
        _plots(stage / "figures", primary, pareto, selection, cfg, results.histograms)
        recommendation = {
            "schema_version": 1, "l": selection.recommended[0], "k": selection.recommended[1],
            "field_set": cfg.field_set, "noise": cfg.primary_noise, "seeds": list(cfg.seeds),
            "selection": "minimum seed-mean validation attack success under the validation F1 budget",
            "f1_budget": cfg.analysis.f1_budget, "validation_f1_floor": selection.minimum_f1,
            "near_ties": [{"l": l, "k": k} for l, k in selection.near_ties],
            "extreme": {"l": selection.extreme[0], "k": selection.extreme[1]},
        }
        meta = {"config": asdict(cfg), "extended": extended, "seed_key_fingerprints": fingerprints,
                "entity_counts": {seed: {name: len(values) for name, values in split.items()}
                                  for seed, split in partitions.items()}}
        for name, obj in (("recommendation", recommendation), ("collision_metadata", meta)):
            (stage / f"{name}.json").write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        summary = _markdown(primary, exact, pareto, cross, effects, trends, controls, gate, cfg, selection)
        (stage / "summary.md").write_text(summary, encoding="utf-8")
        for path in stage.iterdir():
            if path.is_dir():
                target = destination / path.name
                target.mkdir(exist_ok=True)
                for figure in path.iterdir():
                    figure.replace(target / figure.name)
            else:
                path.replace(destination / path.name)
