"""
src/metrics.py
Component 1: Pre-Ledger Cross-Organizational Data Harmonization

Role:
- Evaluates Entity Resolution / Record Linkage performance using Pairwise Metrics.
- Computes True Positives (TP), False Positives (FP), False Negatives (FN), 
  Pairwise Precision, Recall, and F1-Score.
- Utilizes combinatoric cluster-overlap logic (O(N) complexity) to prevent O(N^2) bottlenecks.
- Generates structured summary dictionaries and tables for RQ1, RQ2, and RQ3 reporting.
"""

"""Structural (attack-independent) Bloom-filter metrics."""
import math

import numpy as np


def fill_stats(bf: np.ndarray):
    fill = bf.mean(axis=1)
    return float(fill.mean()), float(fill.std())


def bit_entropy(bf: np.ndarray) -> float:
    """Mean binary entropy (bits) of each bit position across records; max = 1."""
    p = bf.mean(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        h = -(p * np.log2(p) + (1 - p) * np.log2(1 - p))
    return float(np.nan_to_num(h, nan=0.0).mean())


def collision_load(mean_distinct_qgrams: float, k: int, l: int) -> float:
    """k * n_q / l : expected number of q-gram insertions per bit position."""
    return mean_distinct_qgrams * k / l


def expected_fill(load: float) -> float:
    return 1.0 - math.exp(-load)


from typing import Dict, List, Any
import numpy as np
import pandas as pd


class LinkageMetrics:
    """
    Computes standard Record Linkage and Clustering evaluation metrics.
    """

    @staticmethod
    def compute_pairwise_metrics(
        df_results: pd.DataFrame,
        true_id_col: str = "true_entity_id",
        pred_id_col: str = "predicted_cluster_id"
    ) -> Dict[str, Any]:
        """
        Calculates Pairwise Precision, Recall, and F1-Score:
        - True Positive (TP): Pair of records with same true_id and same pred_id.
        - False Positive (FP): Pair of records with different true_id but same pred_id (Over-clustering).
        - False Negative (FN): Pair of records with same true_id but different pred_id (Under-clustering/Fragmentation).

        Mathematical Formulation:
        - Total Positive Pairs in Ground Truth = sum(n_i * (n_i - 1) / 2) for each true entity i.
        - Total Predicted Pairs in Clusters   = sum(m_j * (m_j - 1) / 2) for each predicted cluster j.
        - TP = sum(k_ij * (k_ij - 1) / 2) where k_ij is overlap between true entity i and pred cluster j.
        - FP = Total Predicted Pairs - TP
        - FN = Total Ground Truth Pairs - TP
        - Precision = TP / (TP + FP)
        - Recall    = TP / (TP + FN)
        - F1-Score  = 2 * (Precision * Recall) / (Precision + Recall)
        """
        # Clean and validate input: drop NA and ignore empty/whitespace strings
        df = df_results[[true_id_col, pred_id_col]].dropna().copy()
        df = df[
            (df[true_id_col].astype(str).str.strip() != "") & 
            (df[pred_id_col].astype(str).str.strip() != "")
        ]
        if len(df) == 0:
            return {
                "precision": 0.0, "recall": 0.0, "f1_score": 0.0,
                "tp": 0, "fp": 0, "fn": 0,
                "total_records": 0, "total_clusters": 0
            }

        # 1. Total Positive Pairs in Ground Truth
        true_counts = df[true_id_col].value_counts().values
        total_ground_truth_pairs = int(sum(n * (n - 1) // 2 for n in true_counts if n > 1))

        # 2. Total Pairs in Predicted Clusters
        pred_counts = df[pred_id_col].value_counts().values
        total_predicted_pairs = int(sum(m * (m - 1) // 2 for m in pred_counts if m > 1))

        # 3. True Positives (Overlap contingency)
        overlap = df.groupby([true_id_col, pred_id_col]).size().values
        tp = int(sum(k * (k - 1) // 2 for k in overlap if k > 1))

        # 4. FP and FN
        fp = max(0, total_predicted_pairs - tp)
        fn = max(0, total_ground_truth_pairs - tp)

        # 5. Compute Rates
        # Edge case: if no ground truth pairs exist (all singletons) and no clusters formed pairs, precision & recall are 1.0
        if total_ground_truth_pairs == 0 and total_predicted_pairs == 0:
            precision = 1.0
            recall = 1.0
        else:
            precision = tp / float(tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / float(tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        return {
            "total_records": len(df),
            "unique_true_entities": len(true_counts),
            "predicted_clusters": len(pred_counts),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "total_gt_pairs": total_ground_truth_pairs,
            "total_pred_pairs": total_predicted_pairs
        }

    @staticmethod
    def format_metrics_table(metrics_list: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Converts a list of experiment metric summaries into a formatted pandas DataFrame.
        """
        return pd.DataFrame(metrics_list)

    @staticmethod
    def entity_bootstrap_ci(
        df_results: pd.DataFrame,
        n_bootstrap: int = 1000,
        confidence: float = 0.95,
        random_seed: int = 2026,
    ) -> Dict[str, float]:
        """Bootstrap pairwise metrics by resampling complete true-entity groups."""
        if df_results.empty:
            return {}
        groups = [group for _, group in df_results.groupby("true_entity_id", sort=False)]
        rng = np.random.default_rng(random_seed)
        values = {metric: [] for metric in ("precision", "recall", "f1_score")}
        for _ in range(n_bootstrap):
            sample = [groups[i] for i in rng.integers(0, len(groups), len(groups))]
            replicate = pd.concat(
                [group.assign(_bootstrap_group=position) for position, group in enumerate(sample)],
                ignore_index=True,
            )
            replicate["predicted_cluster_id"] = (
                replicate["_bootstrap_group"].astype(str)
                + ":"
                + replicate["predicted_cluster_id"].astype(str)
            )
            replicate["true_entity_id"] = (
                replicate["_bootstrap_group"].astype(str)
                + ":"
                + replicate["true_entity_id"].astype(str)
            )
            metrics = LinkageMetrics.compute_pairwise_metrics(replicate)
            for metric in values:
                values[metric].append(metrics[metric])
        alpha = (1.0 - confidence) / 2.0
        return {
            f"{metric}_{bound}": float(np.quantile(scores, alpha if bound == "lower" else 1.0 - alpha))
            for metric, scores in values.items()
            for bound in ("lower", "upper")
        }


if __name__ == "__main__":
    # Quick self-test
    test_data = pd.DataFrame([
        {"record_id": "R1", "true_entity_id": "E1", "predicted_cluster_id": "C1"},
        {"record_id": "R2", "true_entity_id": "E1", "predicted_cluster_id": "C1"},  # TP match
        {"record_id": "R3", "true_entity_id": "E2", "predicted_cluster_id": "C2"},
        {"record_id": "R4", "true_entity_id": "E2", "predicted_cluster_id": "C2"},  # TP match
    ])

    metrics = LinkageMetrics.compute_pairwise_metrics(test_data)
    print("--- Linkage Metrics Test ---")
    for k, v in metrics.items():
        print(f"{k:22s}: {v}")