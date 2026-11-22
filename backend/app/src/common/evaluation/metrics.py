"""Compute pairwise linkage and fragmentation metrics from cluster labels."""

from collections.abc import Iterable

import pandas as pd


def _count_pairs(sizes: Iterable[int]) -> int:
    return sum(n * (n - 1) // 2 for n in map(int, sizes))


def evaluate_clusters(
    entity_ids: pd.Series, cluster_labels: pd.Series
) -> dict[str, float | int]:
    """Evaluate aligned, non-null labels using contingency counts.

    Precision is TP / predicted pairs. With zero predicted pairs, precision is
    1.0 if there are also zero true pairs and 0.0 otherwise. Recall is TP / true
    pairs, or 1.0 with zero true pairs. F1 is the harmonic mean, or 0.0 when
    precision and recall sum to zero.

    Fragmentation is the mean distinct predicted clusters per true entity among
    entities with at least two records. It is NaN when there are no such entities.
    """
    if not entity_ids.index.equals(cluster_labels.index):
        raise ValueError("entity_ids and cluster_labels must have the same index in the same order")
    if entity_ids.isna().any() or cluster_labels.isna().any():
        raise ValueError("entity_ids and cluster_labels must both be non-null")

    frame = pd.DataFrame({"entity": entity_ids.array, "cluster": cluster_labels.array})
    cells = frame.groupby(["entity", "cluster"], sort=False, observed=True).size()
    by_entity = cells.groupby(level="entity", sort=False, observed=True)
    entity_sizes = by_entity.sum()
    cluster_sizes = cells.groupby(level="cluster", sort=False, observed=True).sum()

    tp = _count_pairs(cells)
    predicted_pairs = _count_pairs(cluster_sizes)
    true_pairs = _count_pairs(entity_sizes)
    precision = tp / predicted_pairs if predicted_pairs else float(true_pairs == 0)
    recall = tp / true_pairs if true_pairs else 1.0
    # The harmonic mean simplifies to 2 * TP / (predicted pairs + true pairs).
    total_pairs = predicted_pairs + true_pairs
    f1 = 2 * tp / total_pairs if total_pairs else 1.0
    fragmentation = float(by_entity.size()[entity_sizes >= 2].mean())
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fragmentation_rate": fragmentation,
        "n_records": len(frame),
        "n_entities": len(entity_sizes),
        "n_pred_clusters": len(cluster_sizes),
    }
