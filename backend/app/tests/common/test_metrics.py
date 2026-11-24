import math

import pandas as pd
import pytest

from src.common.evaluation.metrics import evaluate_clusters, pairwise_prf


def test_pairwise_empty_counts_follow_the_callers_convention():
    assert pairwise_prf(0, 0, 0) == (1, 1, 1)
    assert pairwise_prf(0, 0, 0, empty_score=0) == (0, 0, 0)
    assert pairwise_prf(0, 3, 0) == (0, 1, 0)
    assert pairwise_prf(0, 3, 0, empty_score=0) == (0, 0, 0)


def _metrics(entities: str, labels: list[int]) -> dict[str, int | float]:
    index = pd.Index([f"r{i}" for i in range(len(entities))])
    return evaluate_clusters(
        pd.Series(list(entities), index=index, dtype=object),
        pd.Series(labels, index=index, dtype=int),
    )


@pytest.mark.parametrize(
    ("entities", "labels", "expected"),
    [
        pytest.param("AABBC", [0, 0, 1, 1, 2], (1.0, 1.0, 1.0, 1.0, 5, 3, 3), id="perfect"),
        pytest.param("AABC", [0, 0, 0, 0], (1 / 6, 1.0, 2 / 7, 1.0, 4, 3, 1), id="one_cluster"),
        pytest.param("AABB", [0, 1, 2, 3], (0.0, 0.0, 0.0, 2.0, 4, 2, 4), id="singletons"),
        pytest.param("AAA", [0, 0, 1], (1.0, 1 / 3, 0.5, 2.0, 3, 1, 2), id="split_entity"),
        pytest.param("AABB", [1, 1, 1, 1], (1 / 3, 1.0, 0.5, 1.0, 4, 2, 1), id="merge_two"),
    ],
)
def test_hand_computed_clusterings(entities, labels, expected):
    assert _metrics(entities, labels) == dict(
        zip(
            ("precision", "recall", "f1", "fragmentation_rate", "n_records", "n_entities", "n_pred_clusters"),
            expected,
        )
    )


def test_mixed_case_counts_and_fragmentation():
    # A occupies clusters 0,1 and B occupies 1,2. C is a singleton in cluster 2.
    # TP = C(2,2) + C(2,2) = 2. True pairs = 3 + 3 = 6.
    # Predicted pairs = 1 + 3 + 1 = 5. Fragmentation = (2 + 2) / 2.
    assert _metrics("AAABBBC", [0, 0, 1, 1, 1, 2, 2]) == {
        "precision": 2 / 5,
        "recall": 2 / 6,
        "f1": 4 / 11,
        "fragmentation_rate": 2.0,
        "n_records": 7,
        "n_entities": 3,
        "n_pred_clusters": 3,
    }


def test_fragmentation_weights_entities_equally_and_excludes_singletons():
    result = _metrics("AAAAABBC", [0, 0, 1, 1, 2, 3, 3, 4])
    assert result["fragmentation_rate"] == (3 + 1) / 2


@pytest.mark.parametrize(
    ("entities", "labels", "expected"),
    [
        ("", [], (1.0, 1.0, 1.0)),
        ("ABC", [0, 1, 2], (1.0, 1.0, 1.0)),
        ("ABC", [0, 0, 0], (0.0, 1.0, 0.0)),
    ],
)
def test_no_true_pairs_conventions(entities, labels, expected):
    result = _metrics(entities, labels)
    assert (result["precision"], result["recall"], result["f1"]) == expected
    assert math.isnan(result["fragmentation_rate"])


def test_mismatched_index_order_raises():
    truth = pd.Series(["A", "A"], index=["r1", "r2"])
    labels = pd.Series([0, 0], index=["r2", "r1"])
    with pytest.raises(ValueError, match="same index"):
        evaluate_clusters(truth, labels)


def test_rejects_incomplete_labels_instead_of_dropping_records():
    with pytest.raises(ValueError, match="non-null"):
        evaluate_clusters(pd.Series(["A", "A"]), pd.Series([0, None]))
