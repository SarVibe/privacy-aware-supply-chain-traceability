from typing import Any, Dict, List

import numpy as np
import pandas as pd


class LinkageMetrics:
    @staticmethod
    def compute_pairwise_metrics(
        df_results: pd.DataFrame,
        true_id_col: str = "true_entity_id",
        pred_id_col: str = "predicted_cluster_id",
    ) -> Dict[str, Any]:
        df = df_results[[true_id_col, pred_id_col]].dropna().copy()
        df = df[
            (df[true_id_col].astype(str).str.strip() != "")
            & (df[pred_id_col].astype(str).str.strip() != "")
        ]
        if len(df) == 0:
            return {
                "precision": 0.0, "recall": 0.0, "f1_score": 0.0,
                "tp": 0, "fp": 0, "fn": 0, "total_records": 0, "total_clusters": 0,
            }

        true_counts = df[true_id_col].value_counts().values
        pred_counts = df[pred_id_col].value_counts().values
        total_ground_truth_pairs = int(sum(n * (n - 1) // 2 for n in true_counts if n > 1))
        total_predicted_pairs = int(sum(n * (n - 1) // 2 for n in pred_counts if n > 1))
        overlap = df.groupby([true_id_col, pred_id_col]).size().values
        tp = int(sum(k * (k - 1) // 2 for k in overlap if k > 1))
        fp = max(0, total_predicted_pairs - tp)
        fn = max(0, total_ground_truth_pairs - tp)

        if total_ground_truth_pairs == 0 and total_predicted_pairs == 0:
            precision = recall = 1.0
        else:
            precision = tp / float(tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / float(tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2.0 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        return {
            "total_records": len(df),
            "unique_true_entities": len(true_counts),
            "predicted_clusters": len(pred_counts),
            "tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "total_gt_pairs": total_ground_truth_pairs,
            "total_pred_pairs": total_predicted_pairs,
        }

    @staticmethod
    def format_metrics_table(metrics_list: List[Dict[str, Any]]) -> pd.DataFrame:
        return pd.DataFrame(metrics_list)

    @staticmethod
    def entity_bootstrap_ci(
        df_results: pd.DataFrame,
        n_bootstrap: int = 1000,
        confidence: float = 0.95,
        random_seed: int = 2026,
    ) -> Dict[str, float]:
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
                replicate["_bootstrap_group"].astype(str) + ":" + replicate["predicted_cluster_id"].astype(str)
            )
            replicate["true_entity_id"] = (
                replicate["_bootstrap_group"].astype(str) + ":" + replicate["true_entity_id"].astype(str)
            )
            result = LinkageMetrics.compute_pairwise_metrics(replicate)
            for metric in values:
                values[metric].append(result[metric])
        alpha = (1.0 - confidence) / 2.0
        return {
            f"{metric}_{bound}": float(np.quantile(scores, alpha if bound == "lower" else 1.0 - alpha))
            for metric, scores in values.items()
            for bound in ("lower", "upper")
        }
