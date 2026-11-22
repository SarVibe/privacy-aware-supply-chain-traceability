from pathlib import Path

import pandas as pd
import pytest

from experiments.rq1 import build_rq1_report
from experiments.rq1.run_rq1 import RAW_COLUMNS, TAU_COLUMNS
from src.common.experiment.io import write_csv

_TABLES = (
    "table1_f1_by_noise", "table2_fragmentation_precision", "table3_ablation_field_set",
    "table4_tau_sensitivity", "table5_paired_difference",
)


def _fixture_inputs(tmp_path: Path, fuzzy_f1: float, seeds: tuple[int, ...]) -> tuple[Path, Path]:
    runs, tuning = [], []
    for seed in seeds:
        for field in ("description", "composite"):
            for noise in (0.0, 0.05, 0.15, 0.30):
                for method, mode, tau, score in (
                    ("raw_exact", "none", None, 0.8),
                    ("normalized_exact", "none", None, 0.85),
                    ("bloom_fuzzy", "single", 0.92, fuzzy_f1),
                    ("bloom_fuzzy", "per_noise", 0.92, 0.99),
                ):
                    runs.append((
                        f"{seed}-{noise}-{field}-{method}-{mode}", seed, noise, method, field,
                        tau, mode, "test", score, score, score, 1.2, 100, 30, 34, 0.01,
                    ))
                tuning.extend([(seed, field, noise, 0.91, 0.8, 0.8, 0.8),
                               (seed, field, noise, 0.92, 0.9, 0.9, 0.9)])
    # A misleading validation row and the sensitivity method must leave the H1 check unchanged.
    runs.append(("validation", 100, 0.05, "bloom_fuzzy", "composite", 0.92, "single", "validation",
                 0.01, 0.01, 0.01, 2.0, 100, 30, 40, 0.01))
    raw_path, tau_path = tmp_path / "raw_runs.csv", tmp_path / "tau_selection.csv"
    write_csv(pd.DataFrame(runs, columns=RAW_COLUMNS), raw_path)
    write_csv(pd.DataFrame(tuning, columns=TAU_COLUMNS), tau_path)
    return raw_path, tau_path


@pytest.mark.parametrize("fuzzy_f1,verdict,seeds", [(0.90, "yes", (0, 1)), (0.79, "no", (0,))])
def test_report_outputs_and_h1_observations(tmp_path, fuzzy_f1, verdict, seeds):
    raw_path, tau_path = _fixture_inputs(tmp_path, fuzzy_f1, seeds)
    out = tmp_path / "report"
    build_rq1_report.main(["--input", str(raw_path), "--tau-input", str(tau_path), "--out-dir", str(out)])
    for name in _TABLES:
        for extension in ("csv", "md", "tex"):
            assert (out / "tables" / f"{name}.{extension}").stat().st_size > 0
        markdown = (out / "tables" / f"{name}.md").read_text(encoding="utf-8")
        assert markdown.rstrip().endswith(build_rq1_report.F1_NOTE)
        assert all(method not in markdown for method in ("raw_exact", "normalized_exact", "bloom_fuzzy"))
        assert "Share of records with typos".lower() in markdown.lower()
        assert "+- –" not in markdown
    for name in ("fig1_f1_vs_noise.png", "fig2_fragmentation_vs_noise.png"):
        assert (out / "figures" / name).read_bytes().startswith(b"\x89PNG")
    note = (out / "h1_check.md").read_text(encoding="utf-8")
    for level in ("5%", "15%", "30%"):
        for method in ("Exact match (cleaned text)", "Exact match (original text)"):
            assert f"At {level} typos, did Fuzzy match (Bloom filter) score higher than {method}? **{verdict}**" in note
    assert f"reach an F1 score of at least 0.90? **{verdict}**" in note
    assert "significant" not in note and "proven" not in note
    f1 = pd.read_csv(out / "tables" / "table1_f1_by_noise.csv", dtype=str).set_index("Method")
    expected = f"{fuzzy_f1:.3f} +- 0.000" if len(seeds) > 1 else f"{fuzzy_f1:.3f}"
    assert f1.loc["Fuzzy match (Bloom filter)", "5%"] == expected
    fragmentation = pd.read_csv(out / "tables" / "table2_fragmentation_precision.csv")
    assert "Average separate groups per product (1.0 = perfect)" in fragmentation
    assert "Precision (share of linked pairs that are correct)" in fragmentation
    ablation = pd.read_csv(out / "tables" / "table3_ablation_field_set.csv")
    assert set(ablation["Fields used"]) == {"Description only", "Description + dosage, form, pack size"}
    assert "Recall (share of true pairs found)" in ablation
    sensitivity = pd.read_csv(out / "tables" / "table4_tau_sensitivity.csv")
    assert sensitivity["Average cutoff across typo levels"].eq(0.92).all()
    assert sensitivity["Average cutoff at this typo level"].eq(0.92).all()
    paired = pd.read_csv(out / "tables" / "table5_paired_difference.csv")
    raw = paired.Comparison.str.endswith("Exact match (original text)")
    assert paired.loc[raw, "Holm-adjusted one-sided p-value"].eq("–").all()
    if len(seeds) == 1:
        assert paired[["Sample standard deviation", "95% interval for the mean difference"]].isna().all().all()
