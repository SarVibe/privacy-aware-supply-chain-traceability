import pandas as pd

from src.rq1.exact_matcher import ExactMatcher
from src.rq1.record_linkage_metrics import LinkageMetrics


def test_raw_exact_matching_does_not_strip_input():
    matcher = ExactMatcher(normalize=False)
    first, _ = matcher.resolve_record("r1", "product")
    second, is_new = matcher.resolve_record("r2", "product ")

    assert first != second
    assert is_new


def test_entity_bootstrap_returns_metric_intervals():
    results = pd.DataFrame([
        {"true_entity_id": "e1", "predicted_cluster_id": "c1"},
        {"true_entity_id": "e1", "predicted_cluster_id": "c1"},
        {"true_entity_id": "e2", "predicted_cluster_id": "c2"},
        {"true_entity_id": "e2", "predicted_cluster_id": "c2"},
    ])

    interval = LinkageMetrics.entity_bootstrap_ci(results, n_bootstrap=20)

    assert interval["f1_score_lower"] <= interval["f1_score_upper"]
