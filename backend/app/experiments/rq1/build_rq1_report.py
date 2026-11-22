"""Build the RQ1 tables, figures, and observational H1 check from saved runs."""

import argparse
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from experiments.rq1.posthoc import POST_HOC_TITLE, post_hoc_destination, protect_frozen_results
from src.common.config import load_config
from src.common.evaluation.aggregation import HYPOTHESIS_NOISE_LEVELS, aggregate_runs, paired_difference
from src.common.experiment.io import read_csv
from src.common.linking.bloom_blocked import BLOOM_BLOCKED
from src.common.linking.exact import NORMALIZED_EXACT, RAW_EXACT
from src.common.linking.threshold import select_per_noise_tau, select_single_tau
from src.common.paths import results_dir
from src.common.reporting.figures import line_chart
from src.common.reporting.tables import MISSING, format_mean_std, save_table

SEED, NOISE, FIELD_SET, METHOD, MODE, SPLIT = (
    "seed", "noise_level", "field_set", "method", "tau_mode", "split"
)
F1, PRECISION, RECALL, FRAGMENTATION = "f1", "precision", "recall", "fragmentation_rate"
MEAN, STD, CI_LOW, CI_HIGH, WINS, N_SEEDS, HOLM = (
    "mean", "std", "ci_low", "ci_high", "wins", "n_seeds", "p_holm"
)
RAW_INPUT, TAU_INPUT = "raw_runs.csv", "tau_selection.csv"
TABLE_DIR, FIGURE_DIR = "tables", "figures"
TABLE_F1 = "table1_f1_by_noise"
TABLE_FRAGMENTATION = "table2_fragmentation_precision"
TABLE_ABLATION = "table3_ablation_field_set"
TABLE_SENSITIVITY = "table4_tau_sensitivity"
TABLE_PAIRED = "table5_paired_difference"
FIGURE_F1 = "fig1_f1_vs_noise.png"
FIGURE_FRAGMENTATION = "fig2_fragmentation_vs_noise.png"
H1_NOTE = "h1_check.md"

FUZZY = "bloom_fuzzy"
METHODS = (RAW_EXACT, NORMALIZED_EXACT, FUZZY)
PRIMARY, ABLATION = "composite", "description"
SINGLE, PER_NOISE, NONE, TEST = "single", "per_noise", "none", "test"
LEVELS = (0.0, *HYPOTHESIS_NOISE_LEVELS)
H1_FLOOR = 0.90

DISPLAY_NAMES = {
    RAW_EXACT: "Exact match (original text)",
    NORMALIZED_EXACT: "Exact match (cleaned text)",
    FUZZY: "Fuzzy match (Bloom filter)",
    BLOOM_BLOCKED: "Fuzzy match + exact dosage/pack blocking (post-hoc)",
    ABLATION: "Description only",
    PRIMARY: "Description + dosage, form, pack size",
    0.0: "0% (control)",
    0.05: "5%",
    0.15: "15%",
    0.30: "30%",
}
METHOD_LABEL, NOISE_LABEL, FIELD_LABEL = "Method", "Share of records with typos", "Fields used"
F1_LABEL = "F1 score (higher is better)"
PRECISION_LABEL = "Precision (share of linked pairs that are correct)"
RECALL_LABEL = "Recall (share of true pairs found)"
FRAGMENTATION_LABEL = "Average separate groups per product (1.0 = perfect)"
DROP_LABEL = "F1 score drop (0% to 30%)"
SENSITIVITY_HEADERS = (
    NOISE_LABEL, f"{F1_LABEL}, one cutoff", f"{F1_LABEL}, cutoff per typo level",
    "Average cutoff across typo levels", "Average cutoff at this typo level",
)
PAIRED_HEADERS = (
    NOISE_LABEL, "Comparison", "Mean F1 score difference", "Sample standard deviation",
    "95% interval for the mean difference", "Wins / seeds", "Holm-adjusted one-sided p-value",
)
F1_TITLE = "How well each method links the same product across typo levels"
FRAGMENTATION_TITLE = "How much each method splits records for the same product"
F1_NOTE = "F1 balances how often predicted links are correct with how many true links the method finds."
POST_HOC_TABLE_TITLES = {
    TABLE_F1: f"{F1_LABEL} by {NOISE_LABEL.lower()}",
    TABLE_FRAGMENTATION: "Separate groups, precision and recall",
    TABLE_PAIRED: "Paired F1 differences versus cleaned-text exact matching",
}


def _number(value: float, digits: int = 3) -> str:
    return MISSING if pd.isna(value) else f"{value:.{digits}f}"


def _score(row: pd.Series, metric: str) -> str:
    mean, std = row[f"{metric}_mean"], row[f"{metric}_std"]
    return _number(mean) if pd.isna(std) else format_mean_std(mean, std)


def _primary_summary(primary: pd.DataFrame, methods: tuple[str, ...] = METHODS) -> pd.DataFrame:
    index = pd.MultiIndex.from_product([methods, LEVELS], names=[METHOD, NOISE])
    return aggregate_runs(primary, [METHOD, NOISE], [F1, PRECISION, FRAGMENTATION, RECALL]).set_index(
        [METHOD, NOISE]
    ).reindex(index)


def _f1_table(summary: pd.DataFrame, methods: tuple[str, ...] = METHODS) -> pd.DataFrame:
    rows = []
    for method in methods:
        scores = summary.loc[method]
        drop = scores.loc[0.0, f"{F1}_mean"] - scores.loc[0.30, f"{F1}_mean"]
        rows.append([DISPLAY_NAMES[method], *[_score(scores.loc[level], F1) for level in LEVELS], _number(drop)])
    return pd.DataFrame(rows, columns=[METHOD_LABEL, *[DISPLAY_NAMES[level] for level in LEVELS], DROP_LABEL])


def _fragmentation_table(summary: pd.DataFrame, include_recall: bool = False) -> pd.DataFrame:
    headers = [METHOD_LABEL, NOISE_LABEL, FRAGMENTATION_LABEL, PRECISION_LABEL]
    metrics = [FRAGMENTATION, PRECISION]
    if include_recall:
        headers.append(RECALL_LABEL)
        metrics.append(RECALL)
    rows = [
        (DISPLAY_NAMES[method], DISPLAY_NAMES[level], *[_score(row, metric) for metric in metrics])
        for (method, level), row in summary.iterrows()
    ]
    return pd.DataFrame(rows, columns=headers)


def _ablation_table(fuzzy: pd.DataFrame) -> pd.DataFrame:
    single = fuzzy.loc[fuzzy[MODE].eq(SINGLE)]
    index = pd.MultiIndex.from_product([[ABLATION, PRIMARY], LEVELS], names=[FIELD_SET, NOISE])
    scores = aggregate_runs(single, [FIELD_SET, NOISE], [F1, PRECISION, RECALL]).set_index(
        [FIELD_SET, NOISE]
    ).reindex(index)
    rows = [
        (DISPLAY_NAMES[field], DISPLAY_NAMES[level], *[_score(row, metric) for metric in (F1, PRECISION, RECALL)])
        for (field, level), row in scores.iterrows()
    ]
    return pd.DataFrame(rows, columns=[FIELD_LABEL, NOISE_LABEL, F1_LABEL, PRECISION_LABEL, RECALL_LABEL])


def _tau_sensitivity(fuzzy: pd.DataFrame, tuning: pd.DataFrame) -> pd.DataFrame:
    composite = fuzzy.loc[fuzzy[FIELD_SET].eq(PRIMARY)]
    index = pd.MultiIndex.from_product([[SINGLE, PER_NOISE], LEVELS], names=[MODE, NOISE])
    scores = aggregate_runs(composite, [MODE, NOISE], [F1]).set_index([MODE, NOISE]).reindex(index)
    selected = tuning.loc[tuning[FIELD_SET].eq(PRIMARY)]
    choices = {
        seed: (select_single_tau(group), select_per_noise_tau(group))
        for seed, group in selected.groupby(SEED, sort=False)
    }
    rows = []
    for level in LEVELS:
        seeds = composite.loc[composite[NOISE].eq(level), SEED].unique()
        if any(seed not in choices or level not in choices[seed][1] for seed in seeds):
            raise ValueError(f"Missing validation tau scores for composite at {level:.0%}")
        single_mean = pd.Series([choices[seed][0] for seed in seeds], dtype=float).mean()
        per_noise_mean = pd.Series([choices[seed][1][level] for seed in seeds], dtype=float).mean()
        rows.append((
            DISPLAY_NAMES[level], _score(scores.loc[(SINGLE, level)], F1),
            _score(scores.loc[(PER_NOISE, level)], F1), _number(single_mean), _number(per_noise_mean),
        ))
    return pd.DataFrame(rows, columns=SENSITIVITY_HEADERS)


def _paired_table(primary: pd.DataFrame, post_hoc: bool = False) -> pd.DataFrame:
    inputs = primary.loc[primary[NOISE].isin(HYPOTHESIS_NOISE_LEVELS)]
    comparisons_to_run = ((FUZZY, NORMALIZED_EXACT), (FUZZY, RAW_EXACT))
    if post_hoc:
        # Each selected method has a single representation here. Pair methods on the
        # same seed and noise level even though blocked matching uses description Dice.
        inputs = inputs.assign(**{FIELD_SET: PRIMARY})
        comparisons_to_run = ((FUZZY, NORMALIZED_EXACT), (BLOOM_BLOCKED, NORMALIZED_EXACT))
    rows = []
    for method, baseline in comparisons_to_run:
        comparisons = paired_difference(
            inputs, {METHOD: method}, {METHOD: baseline}, F1, infer=baseline == NORMALIZED_EXACT
        ).set_index(NOISE)
        for level in HYPOTHESIS_NOISE_LEVELS:
            comparison = f"{DISPLAY_NAMES[method]} minus {DISPLAY_NAMES[baseline]}"
            if level not in comparisons.index:
                rows.append((DISPLAY_NAMES[level], comparison, MISSING, MISSING, MISSING, "0/0", MISSING))
                continue
            row = comparisons.loc[level]
            interval = ""
            if pd.notna(row[CI_LOW]) and pd.notna(row[CI_HIGH]):
                interval = f"[{_number(row[CI_LOW])}, {_number(row[CI_HIGH])}]"
            rows.append((
                DISPLAY_NAMES[level], comparison, _number(row[MEAN]),
                "" if pd.isna(row[STD]) else _number(row[STD]), interval,
                f"{int(row[WINS])}/{int(row[N_SEEDS])}", _number(row[HOLM], 4),
            ))
    return pd.DataFrame(rows, columns=PAIRED_HEADERS)


def _h1_note(summary: pd.DataFrame) -> str:
    def verdict(condition: bool, *values: float) -> str:
        if any(pd.isna(value) for value in values):
            return "unavailable"
        return "yes" if condition else "no"

    means = summary[f"{F1}_mean"]
    lines = [
        "# Observed mean F1 on the test split", "",
        f"Fields used are {DISPLAY_NAMES[PRIMARY]}. The fuzzy method uses one cutoff across all typo levels.", "",
    ]
    for level in HYPOTHESIS_NOISE_LEVELS:
        fuzzy = means.loc[(FUZZY, level)]
        for baseline in (NORMALIZED_EXACT, RAW_EXACT):
            exact = means.loc[(baseline, level)]
            lines.append(
                f"- At {DISPLAY_NAMES[level]} typos, did {DISPLAY_NAMES[FUZZY]} score higher than "
                f"{DISPLAY_NAMES[baseline]}? "
                f"**{verdict(fuzzy > exact, fuzzy, exact)}** ({_number(fuzzy, 4)} vs {_number(exact, 4)})."
            )
    fuzzy_at_five = means.loc[(FUZZY, HYPOTHESIS_NOISE_LEVELS[0])]
    lines.append(
        f"- At {DISPLAY_NAMES[HYPOTHESIS_NOISE_LEVELS[0]]} typos, did {DISPLAY_NAMES[FUZZY]} "
        f"reach an F1 score of at least {H1_FLOOR:.2f}? "
        f"**{verdict(fuzzy_at_five >= H1_FLOOR, fuzzy_at_five)}** ({_number(fuzzy_at_five, 4)})."
    )
    return "\n".join(lines) + "\n"


def build_report(input_path: Path, tau_input: Path, out_dir: Path) -> None:
    """Create the five tables, two figures, and observational note from saved results."""
    cfg = load_config("rq1")
    protect_frozen_results(cfg, out_dir)
    runs = read_csv(input_path)
    tuning = read_csv(tau_input)
    test = runs.loc[runs[SPLIT].eq(TEST)]
    fuzzy = test.loc[test[METHOD].eq(FUZZY)]
    blocked = test.loc[test[METHOD].eq(BLOOM_BLOCKED) & test[FIELD_SET].eq(ABLATION) & test[MODE].eq(SINGLE)]
    post_hoc = runs[METHOD].eq(BLOOM_BLOCKED).any()
    methods = METHODS
    if post_hoc:
        out_dir = post_hoc_destination(cfg, out_dir)
        methods = (*METHODS, BLOOM_BLOCKED)
    primary = test.loc[
        test[FIELD_SET].eq(PRIMARY)
        & ((test[METHOD].eq(FUZZY) & test[MODE].eq(SINGLE))
           | (test[METHOD].isin((RAW_EXACT, NORMALIZED_EXACT)) & test[MODE].eq(NONE)))
    ]
    if primary.empty:
        raise ValueError("The input has no primary composite test results")
    if post_hoc:
        if blocked.empty:
            raise ValueError("The post-hoc input has no blocked test results")
        primary = pd.concat([primary, blocked], ignore_index=True)
    if primary.duplicated(subset=[SEED, METHOD, NOISE]).any():
        raise ValueError("Expected one primary test row per seed, method and noise level")
    summary = _primary_summary(primary, methods)
    tables = out_dir / TABLE_DIR
    figures = out_dir / FIGURE_DIR
    if post_hoc:
        tables, figures = (post_hoc_destination(cfg, path) for path in (tables, figures))
    report_tables = [
        (TABLE_F1, _f1_table(summary, methods)),
        (TABLE_FRAGMENTATION, _fragmentation_table(summary, include_recall=post_hoc)),
    ]
    if not post_hoc:
        report_tables.extend(((TABLE_ABLATION, _ablation_table(fuzzy)), (TABLE_SENSITIVITY, _tau_sensitivity(fuzzy, tuning))))
    report_tables.append((TABLE_PAIRED, _paired_table(primary, post_hoc)))
    for name, table in report_tables:
        base = tables / name
        save_table(table, base)
        markdown = base.with_suffix(".md")
        caption = f"**{F1_LABEL} by {NOISE_LABEL.lower()}**\n\n" if name == TABLE_F1 else ""
        if post_hoc:
            title = f"{POST_HOC_TITLE}: {POST_HOC_TABLE_TITLES[name]}"
            caption = f"## {title}\n\n"
            latex = base.with_suffix(".tex")
            body = latex.read_text(encoding="utf-8")
            latex_title = title.replace("%", r"\%")
            latex.write_text(f"\\begin{{table}}\n\\caption{{{latex_title}}}\n{body}\\end{{table}}\n", encoding="utf-8")
        markdown.write_text(f"{caption}{markdown.read_text(encoding='utf-8')}\n{F1_NOTE}\n", encoding="utf-8")

    plot = summary.reset_index()
    plot[METHOD] = plot[METHOD].map(DISPLAY_NAMES)
    plot[NOISE] = pd.Categorical(
        plot[NOISE].map(DISPLAY_NAMES), categories=[DISPLAY_NAMES[level] for level in LEVELS], ordered=True,
    )
    prefix = f"{POST_HOC_TITLE}: " if post_hoc else ""
    line_chart(
        plot, NOISE, f"{F1}_mean", f"{F1}_std", METHOD, prefix + F1_TITLE, NOISE_LABEL,
        F1_LABEL, figures / FIGURE_F1,
    )
    line_chart(
        plot, NOISE, f"{FRAGMENTATION}_mean", f"{FRAGMENTATION}_std", METHOD,
        prefix + FRAGMENTATION_TITLE, NOISE_LABEL, FRAGMENTATION_LABEL, figures / FIGURE_FRAGMENTATION,
        score_axis=False,
    )
    if not post_hoc:
        (out_dir / H1_NOTE).write_text(_h1_note(summary), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    """Build an RQ1 report from the command line."""
    default = results_dir(load_config("rq1"), "rq1")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=default / RAW_INPUT)
    parser.add_argument("--tau-input", type=Path, default=default / TAU_INPUT)
    parser.add_argument("--out-dir", type=Path, default=default)
    args = parser.parse_args(argv)
    try:
        build_report(args.input, args.tau_input, args.out_dir)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"RQ1 report written to {args.out_dir.resolve()}")


if __name__ == "__main__":
    main()
