"""Generate the frozen v2 figures and report from validated tables."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.common.reporting.tables import format_mean_std
from src.rq2.collision_v2_analysis import PRECISION, compute_v2_analysis
from src.rq2.collision_v2_artifacts import export_v2_csv
from src.rq2.collision_v2_metrics import E2

DISCLOSURE = ("v2 endpoints were defined after observing v1 results and are a methodological refinement, "
              "not independent confirmation of the original hypotheses")


def _v2_plots(directory, tables, histograms, cfg):
    directory.mkdir()
    points, analytical, runs = (tables[name] for name in ("pareto", "analytical", "per_run"))
    analytical = _primary(analytical, cfg)
    runs = _primary(runs, cfg)
    primary = _primary(tables["aggregated"], cfg)
    fig, ax = plt.subplots(figsize=(7, 5), layout="constrained")
    ax.scatter(points[PRECISION], points["f1"], label="Bloom grid")
    front = points.loc[points["pareto"]].sort_values(PRECISION)
    ax.plot(front[PRECISION], front["f1"], color="#26828e", alpha=0.65)
    baseline = points.loc[points["l"].eq(cfg.baseline[0]) & points["k"].eq(cfg.baseline[1])]
    for rows, name, marker in ((baseline, "Baseline 2", "s"), (points.loc[points["recommended"]], "Recommended", "*")):
        ax.scatter(rows[PRECISION], rows["f1"], label=name, marker=marker, s=130)
    ax.set(xlabel="Known-key candidate precision", ylabel="Pairwise cluster F1", title="Empirical privacy and utility")
    ax.legend()
    _save_v2(fig, directory, "privacy_vs_f1")

    fig, axes = plt.subplots(2, 2, figsize=(10, 7), layout="constrained")
    charts = ((PRECISION, "Known-key candidate precision"), ("excess_matched", "Matched excess"),
              ("f1", "Pairwise cluster F1"), ("fill", "Fill ratio"))
    for ax, (value, title) in zip(axes.flat, charts, strict=True):
        grid = primary.pivot(index="l", columns="k", values=f"{value}_mean").sort_index(ascending=False)
        matrix = grid.to_numpy()
        plot = ax.imshow(matrix, cmap="viridis", aspect="auto")
        ax.set(xticks=range(len(grid.columns)), xticklabels=grid.columns, yticks=range(len(grid.index)),
               yticklabels=grid.index, xlabel="k", ylabel="l", title=title)
        for (i, j), value in np.ndenumerate(matrix):
            color = "black" if plot.norm(value) > 0.58 else "white"
            ax.text(j, i, f"{value:.3f}", ha="center", va="center", color=color)
        fig.colorbar(plot, ax=ax, shrink=0.7)
    _save_v2(fig, directory, "grid_heatmaps")

    fig, axes = plt.subplots(2, 2, figsize=(10, 7), layout="constrained")
    for ax, (metric, title) in zip(axes.flat, ((*charts[:3], ("ambiguity_mean", "Mean tokens per bit"))), strict=True):
        for length, group in runs.groupby("l"):
            ax.scatter(group["fill"], group[metric], label=f"l={length}", alpha=0.7, s=22)
        ax.axvline(0.5, color="0.6", linewidth=0.8)
        ax.set(xlabel="Measured fill", ylabel=title)
    axes[0, 0].legend()
    _save_v2(fig, directory, "outcomes_vs_fill")

    fig, axes = plt.subplots(1, analytical["l"].nunique(), figsize=(12, 4), layout="constrained")
    for ax, (length, group) in zip(np.atleast_1d(axes), analytical.groupby("l"), strict=True):
        group = group.sort_values("k")
        ax.plot(group["k"], group["e2_false_candidates"], "o-", label="Observed")
        ax.plot(group["k"], group["false_candidates_finite"], "s--", label="Finite-length expectation")
        ax.axvline(group["k_opt"].mean(), color="#9a4716", linestyle=":", label="Continuous k_opt")
        ax.set(xlabel="k", ylabel="Mean false candidates per record", title=f"l={length}", yscale="symlog")
    np.atleast_1d(axes)[0].legend(fontsize=8)
    _save_v2(fig, directory, "false_candidates_vs_k")

    role_cells = {cfg.baseline: ["Baseline 2"]}
    for role, name in (("recommended", "Recommended"), ("extreme", "Lowest validation E2 precision")):
        row = points.loc[points[role]].iloc[0]
        role_cells.setdefault((row["l"], row["k"]), []).append(name)
    fig, axes = plt.subplots(1, len(role_cells), figsize=(4.7 * len(role_cells), 4), layout="constrained", sharey=True)
    edges = np.linspace(0, 1, cfg.analysis.histogram_bins + 1)
    for ax, (cell, names) in zip(np.atleast_1d(axes), role_cells.items(), strict=True):
        for field, title in (("match", "Match"), ("nonmatch", "Non-match")):
            counts = np.sum([getattr(separation, field) for separation in histograms[cell]], axis=0)
            if counts.sum():
                ax.stairs(counts / counts.sum(), edges, label=title)
        ax.set(xlabel="Raw Dice", title=f"{' / '.join(names)}\nl={cell[0]}, k={cell[1]}", xlim=(0, 1))
    np.atleast_1d(axes)[0].set_ylabel("Fraction of pairs per bin")
    np.atleast_1d(axes)[0].legend()
    _save_v2(fig, directory, "dice_distributions")


def _save_v2(fig, directory, name):
    fig.savefig(directory / f"{name}.png", dpi=160)
    plt.close(fig)


def _primary(table, cfg):
    return table.loc[table["variant"].eq("description") & table["noise"].eq(cfg.primary_noise)]


def _metric_view(frame, metrics):
    display = frame[["l", "k"]].copy()
    for metric in metrics:
        display[metric] = [
            format_mean_std(mean, std, digits=5) for mean, std in
            zip(frame[f"{metric}_mean"], frame[f"{metric}_std"], strict=True)
        ]
    return display.to_markdown(index=False)


def _v2_summary(tables, recommendation, metadata, cfg):
    primary = _primary(tables["aggregated"], cfg)
    analytical = _primary(tables["analytical"], cfg)
    controls = tables["controls"].groupby("split", as_index=False).agg(
        hit=("hit", "mean"), matched_null=("null_matched", "mean"),
        random_hit=("random_hit", "mean"), max_gap=("random_gap", "max"),
    )
    controls["matched_lift"] = controls["hit"] / controls["matched_null"]
    sensitivity = tables["tau_sensitivity"]
    sensitivity = _primary(sensitivity.loc[sensitivity["split"].eq("test")], cfg)
    sensitivity_cols = ["seed", "l", "k", "tau", "f1", "direct_f1", "closure_added_false"]
    cross_cols = ["variant", "noise", "l", "k", "f1_mean", "f1_delta_vs_baseline", f"{PRECISION}_mean",
                  f"{PRECISION}_delta_vs_baseline", "excess_matched_mean"]
    h1_effects = tables["paired_effects"]
    h1_effects = h1_effects.loc[h1_effects["metric"].eq("excess_matched"),
                              ["l", "k", "mean_difference", "ci_low", "ci_high", "rank_biserial"]]
    exact = tables["exact_baseline"]
    exact_scores = ", ".join(f"{name} {format_mean_std(exact[name].mean(), exact[name].std(), digits=5)}"
                             for name in ("precision", "recall", "f1", "pr_auc", "dice_overlap"))
    rec = recommendation
    role = f"({rec['l']}, {rec['k']})"
    return "\n".join([
        "# RQ2 v2 empirical collision benchmark", "",
        "## V1 recap and audit findings", "",
        "V1 found that shorter filters raised raw bit-membership hit rate and ambiguity. Its full-universe random baseline "
        "used a wider token pool than the aligner, and the saturated cell produced one cluster in every seed. The V1 "
        "post-hoc supplement reports excess and lift from saved CSVs. The ephemeral V1 key prevents recovery of matched "
        "nulls and known-key metrics.", "",
        "## V2 rationale", "", DISCLOSURE + ".", "",
        "## Protocol", "",
        f"Frozen protocol commit `{metadata['protocol_commit']}`. The main grid used seeds {list(cfg.seeds)}, "
        f"{cfg.primary_noise:.0%} description noise, entity-disjoint validation/test/reference within each seed, "
        "and a fixed environment-derived research key. Each cell selected tau on validation. Test metrics and the "
        "above-ceiling sensitivity were reported separately. All measurements are empirical.", "",
        "## Controls and E1 bit-membership hit rate", "", controls.to_markdown(index=False, floatfmt=".6f"), "",
        _metric_view(primary, ("hit", "null_matched", "excess_matched", "lift_matched",
                               "null_full", "excess_full", "lift_full")), "",
        "The database-frequency variant uses its own matched candidate pool and is a sensitivity comparison.", "",
        "## E2 known-key membership and analytical reference", "",
        _metric_view(primary, E2), "",
        analytical.to_markdown(index=False, floatfmt=".6g"), "",
        "The finite-length column averages the ideal absent-query expectation over records. The exponential fill and "
        "whole-universe candidate count are approximations. Occupancy entropy follows the binary entropy identity.", "",
        "## Utility and direct-edge diagnostics", "",
        f"Normalized keyed exact baseline test mean and sample SD were {exact_scores}.", "",
        _metric_view(primary, ("precision", "recall", "f1", "pr_auc", "dice_overlap", "direct_precision", "direct_recall",
                               "direct_f1", "direct_false", "cluster_false", "closure_added_false")), "",
        "## Tau-ceiling sensitivity", "",
        (sensitivity[sensitivity_cols].to_markdown(index=False, floatfmt=".5f") if not sensitivity.empty
         else "No primary cell selected the cutoff ceiling."), "",
        "## Hypothesis outcomes", "", tables["hypotheses"].to_markdown(index=False), "",
        "The intervals are paired percentile bootstrap intervals. Pooled correlations and intervals are descriptive "
        "because seeds reuse entities.", "",
        "### H1'-b matched-excess intervals versus Baseline 2", "",
        h1_effects.to_markdown(index=False, floatfmt=".6f"), "",
        "### H3' reduction and paired F1 intervals", "", tables["h3"].to_markdown(index=False, floatfmt=".6f"), "",
        "All pooled trends and paired effects are in `trends.csv` and `paired_effects.csv`.", "",
        "## Recommendation and cross-check", "",
        f"Validation selected {role} with E2 precision {rec['validation_e2_precision']:.5f} and F1 "
        f"{rec['validation_f1']:.5f} under an F1 floor of {rec['minimum_validation_f1']:.5f}. Held-out E2 precision "
        f"was {rec['test_e2_precision']:.5f} and F1 was {rec['test_f1']:.5f}. Eligible near-ties were "
        f"{rec['near_ties'] or 'none'}. The lowest unrestricted validation E2 precision cell was {rec['extreme']}.", "",
        tables["cross_check"][cross_cols].to_markdown(index=False, floatfmt=".5f"), "",
        "Pareto membership uses held-out E2 precision and F1. The owner controls any downstream adoption.", "",
        "## Limitations", "",
        "- The evaluation measures empirical privacy under two specific endpoints on one dataset. RQ3 addresses formal privacy.",
        "- The seeds are overlapping resamples. The overlap table records pairwise test overlap and pilot-to-test overlap.",
        "- Occupancy and ambiguity depend on composite Q. Under description-only noise, clean dosage, form and pack fields "
        "also contribute to the ground truth. The all-fields row uses separately generated observations.",
        "- The known-key calculation uses the evaluator's favorable target-plus-reference vocabulary. A candidate set "
        "describes token membership under that vocabulary and does not establish recovery of source records or identities.",
        "- The pilot checked correctness and runtime. V2 endpoints and hypotheses were chosen after V1 results.", "",
    ])


def write_v2_run_artifacts(results, controls, overlap, destination: Path, cfg, metadata, selection=None):
    destination.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination) as temporary:
        stage = Path(temporary)
        raw = {name: getattr(results, name) for name in ("per_run", "exact_baseline", "e1", "e2", "tau_sweeps",
                                                         "tau_sensitivity", "validation")}
        tables = {name: export_v2_csv(name, rows, stage) for name, rows in
                  {**raw, "controls": controls, "overlap": overlap}.items()}
        if selection is not None:
            recommended, extreme, floor, choices = selection
            analysis = compute_v2_analysis(tables["per_run"], choices, cfg)
            tables.update({name: export_v2_csv(name, frame, stage) for name, frame in analysis.items()})
            points = tables["pareto"]
            chosen = points.loc[points["recommended"]].iloc[0]
            recommendation = {"schema_version": 2, "field_set": cfg.field_set, "l": recommended[0],
                              "k": recommended[1], "seeds": list(cfg.seeds), "noise": cfg.primary_noise,
                              "validation_e2_precision": float(chosen["validation_e2_precision"]),
                              "validation_f1": float(chosen["validation_f1"]), "minimum_validation_f1": floor,
                              "test_f1": float(chosen["f1"]), "test_e2_precision": float(chosen[PRECISION]),
                              "near_ties": points.loc[points["near_tie"], ["l", "k"]].to_dict("records"),
                              "extreme": {"l": extreme[0], "k": extreme[1]}}
            (stage / "recommendation_v2.json").write_text(json.dumps(recommendation, indent=2, allow_nan=False) + "\n",
                                                          encoding="utf-8")
            _v2_plots(stage / "figures", tables, results.histograms, cfg)
            (stage / "summary_v2.md").write_text(_v2_summary(tables, recommendation, metadata, cfg), encoding="utf-8")
        else:
            (stage / "summary_pilot.md").write_text(
                f"# RQ2 v2 correctness pilot\n\n{DISCLOSURE}.\n\n"
                f"The pilot evaluated {len(tables['per_run'])} cells on seed {cfg.pilot.seed}. "
                f"Grid scoring took {metadata['grid_seconds']:.3f} seconds. "
                "The above-ceiling sweep, direct-edge diagnostics, endpoints and CSV schemas used the frozen protocol. "
                "The overlap table records intersections with final test splits. No recommendation was selected.\n",
                encoding="utf-8",
            )
        (stage / "metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        for artifact in stage.iterdir():
            if artifact.is_dir():
                target = destination / artifact.name
                target.mkdir(exist_ok=True)
                for figure in artifact.iterdir():
                    figure.replace(target / figure.name)
            else:
                artifact.replace(destination / artifact.name)
