import ast
from math import isnan, sqrt
from pathlib import Path

import pandas as pd
import pytest

from experiments.rq2 import results_analyzer
from src.common.evaluation.aggregation import mean_ci95_half_width


EXPECTED_HALF_WIDTH = 4.302652729911275 * 0.02 / sqrt(3)


def test_interval_matches_hand_computed_student_t_half_width():
    assert mean_ci95_half_width([0.80, 0.82, 0.84]) == pytest.approx(EXPECTED_HALF_WIDTH, rel=0, abs=1e-9)


@pytest.mark.parametrize("values", [[], [0.80], [0.80, float("nan"), 0.84]])
def test_interval_returns_nan_for_insufficient_or_missing_values(values):
    assert isnan(mean_ci95_half_width(values))


def test_interval_is_zero_for_constant_values():
    assert mean_ci95_half_width([0.80, 0.80, 0.80]) == 0.0


def test_rq2_aggregates_intervals_for_two_configurations_across_three_seeds():
    results = pd.DataFrame({
        "seed": [0, 1, 2, 0, 1, 2],
        "l": [1024, 1024, 1024, 512, 512, 512],
        "k": [4, 4, 4, 4, 4, 4],
        "f1": [0.80, 0.82, 0.84, 0.67, 0.69, 0.71],
    })
    summary = results_analyzer.aggregate(results, ["l", "k"]).set_index(["l", "k"])
    assert summary["n_seeds"].to_dict() == {(512, 4): 3, (1024, 4): 3}
    assert summary["f1_mean"].tolist() == pytest.approx([0.69, 0.82])
    assert summary["f1_ci95"].tolist() == pytest.approx([EXPECTED_HALF_WIDTH] * 2, rel=0, abs=1e-9)


def test_analysis_and_shared_source_have_no_undefined_names():
    checker = pytest.importorskip("pyflakes.checker", reason="Pyflakes is unavailable. Use the standalone AST audit.")
    from pyflakes.messages import UndefinedName

    app = Path(__file__).resolve().parents[2]
    issues = []
    for directory in ("src", "experiments"):
        for path in sorted((app / directory).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            issues.extend(
                str(message) for message in checker.Checker(tree, filename=str(path)).messages
                if isinstance(message, UndefinedName)
            )
    assert not issues, "\n".join(issues)
