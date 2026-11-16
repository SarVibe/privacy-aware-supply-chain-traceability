"""
experiments/exp1_accuracy_benchmark.py
Component 1: Experimental Evaluation Engine

Role:
- Executes Research Question 1 (RQ1): Linkage Accuracy Benchmark under Typographical Noise.
- Compares Proposed Keyed Bloom Filter (Algorithm 1) against Baseline Exact Hash Matching.
- Evaluates across 0%, 5%, 15%, and 30% synthetic typographical noise levels.
- Computes Pairwise Precision, Recall, and F1-Score using LinkageMetrics.
- Generates publication-ready figures and LaTeX/CSV summary tables in results/.
"""

import os
import tempfile
# Redirect matplotlib cache to writable temp directory to avoid Windows permission latency
os.environ["MPLCONFIGDIR"] = os.path.join(tempfile.gettempdir(), "matplotlib_c1_cache")

import logging
from typing import Optional, List
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Headless visualization
import matplotlib.pyplot as plt
import seaborn as sns

from src.config import Config
from src.exact_matcher import ExactMatcher
from src.preprocessor import TextPreprocessor
from src.keyed_bloom_filter import KeyedBloomFilter
from src.entity_resolver import EntityResolver
from src.metrics import LinkageMetrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class Experiment1AccuracyBenchmark:
    """
    Executes and visualizes RQ1 Linkage Accuracy Benchmark across noise levels and thresholds.
    """

    def __init__(self, thresholds: Optional[List[float]] = None):
        Config.ensure_directories()
        self.noise_levels = Config.RQ1_NOISE_LEVELS  # [0, 5, 15, 30]
        self.thresholds = thresholds or [0.80, 0.85, 0.90, 0.92, 0.94, 0.96]
        self.exact_matcher = ExactMatcher()
        self.bf_engine = KeyedBloomFilter(
            length=Config.DEFAULT_BF_LENGTH,
            num_hashes=Config.DEFAULT_NUM_HASHES
        )

    def _load_noisy_dataset(self, noise_pct: int) -> pd.DataFrame:
        """Loads synthetic noisy dataset generated for the given noise percentage."""
        path = os.path.join(Config.DATA_SYNTHETIC_DIR, f"noisy_products_{noise_pct}.csv")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing dataset {path}. Run 'python -m experiments.noise_generator' first.")
        return pd.read_csv(path)

    def run_baseline_exact(self, df_noisy: pd.DataFrame) -> dict:
        """Runs Exact Hash Matching Baseline."""
        self.exact_matcher.reset()
        df_res = self.exact_matcher.process_dataset(
            df_noisy,
            text_column="raw_item_description",
            id_column="record_id"
        )
        metrics = LinkageMetrics.compute_pairwise_metrics(df_res)
        return metrics

    def run_proposed_fuzzy(self, df_noisy: pd.DataFrame, threshold: float = Config.DEFAULT_SIMILARITY_THRESHOLD) -> dict:
        """
        Runs Proposed Keyed Bloom Filter Matching (Algorithm 1) under specified threshold
        using Optimal Composite Multi-Attribute Representation: Tag(Name) ∪ Tag(Dosage) ∪ Tag(Dosage Form) ∪ Tag(Pack Size).
        """
        resolver = EntityResolver(threshold=threshold)

        records_to_process = []
        for _, row in df_noisy.iterrows():
            comp_qgrams = TextPreprocessor.extract_composite_qgrams(
                text=str(row["raw_item_description"]),
                dosage=row.get("dosage", None),
                dosage_form=row.get("dosage_form", None),
                pack_size=row.get("pack_size", None),
                q=Config.DEFAULT_Q
            )
            bf = self.bf_engine.encode(comp_qgrams)

            records_to_process.append({
                "record_id": str(row["record_id"]),
                "true_entity_id": str(row["true_entity_id"]),
                "bloom_filter": bf
            })

        df_res = resolver.process_dataset(records_to_process)
        metrics = LinkageMetrics.compute_pairwise_metrics(df_res)
        return metrics

    def execute_benchmark(self) -> pd.DataFrame:
        """
        Runs the full comparison across all noise levels and threshold calibrations.
        """
        results = []
        logger.info("=================================================================")
        logger.info("Executing RQ1 Accuracy Benchmark (Exact vs Fuzzy Multi-Threshold)")
        logger.info(f"Thresholds evaluated: {self.thresholds}")
        logger.info("=================================================================")

        for noise in self.noise_levels:
            logger.info(f"--- Evaluating Noise Level: {noise}% ---")
            df_noisy = self._load_noisy_dataset(noise)

            # 1. Run Baseline Exact
            m_exact = self.run_baseline_exact(df_noisy)
            results.append({
                "method": "Baseline (Exact Matching)",
                "threshold": 1.0,
                "noise_level_pct": noise,
                "precision": m_exact["precision"],
                "recall": m_exact["recall"],
                "f1_score": m_exact["f1_score"],
                "tp": m_exact["tp"],
                "fp": m_exact["fp"],
                "fn": m_exact["fn"]
            })

            # 2. Run Proposed Fuzzy across each threshold
            for tau in self.thresholds:
                m_fuzzy = self.run_proposed_fuzzy(df_noisy, threshold=tau)
                results.append({
                    "method": f"Proposed (Keyed BF, tau={tau:.2f})",
                    "threshold": tau,
                    "noise_level_pct": noise,
                    "precision": m_fuzzy["precision"],
                    "recall": m_fuzzy["recall"],
                    "f1_score": m_fuzzy["f1_score"],
                    "tp": m_fuzzy["tp"],
                    "fp": m_fuzzy["fp"],
                    "fn": m_fuzzy["fn"]
                })

        df_summary = pd.DataFrame(results)

        # Save summary CSV
        csv_out = os.path.join(Config.TABLES_DIR, "rq1_accuracy_benchmark.csv")
        df_summary.to_csv(csv_out, index=False)
        logger.info(f"Saved benchmark summary table -> {csv_out}")

        return df_summary

    def plot_results(self, df_summary: pd.DataFrame):
        """
        Plots publication-quality comparative line graphs for Precision, Recall, and F1 across thresholds.
        """
        sns.set_theme(style="whitegrid", font_scale=1.1)
        _, axes = plt.subplots(1, 3, figsize=(19, 5.5), sharey=True)

        metrics = ["precision", "recall", "f1_score"]
        titles = ["(a) Pairwise Precision", "(b) Pairwise Recall", "(c) Pairwise F1-Score"]

        # Color palette for thresholds
        palette = {
            "Baseline (Exact Matching)": "#2c3e50",
            "Proposed (Keyed BF, tau=0.80)": "#9b59b6",
            "Proposed (Keyed BF, tau=0.85)": "#e74c3c",
            "Proposed (Keyed BF, tau=0.90)": "#e67e22",
            "Proposed (Keyed BF, tau=0.92)": "#f1c40f",
            "Proposed (Keyed BF, tau=0.94)": "#3498db",
            "Proposed (Keyed BF, tau=0.96)": "#2ecc71"
        }
        markers = {
            "Baseline (Exact Matching)": "X",
            "Proposed (Keyed BF, tau=0.80)": "v",
            "Proposed (Keyed BF, tau=0.85)": "s",
            "Proposed (Keyed BF, tau=0.90)": "^",
            "Proposed (Keyed BF, tau=0.92)": "D",
            "Proposed (Keyed BF, tau=0.94)": "P",
            "Proposed (Keyed BF, tau=0.96)": "o"
        }

        for i, metric in enumerate(metrics):
            ax = axes[i]
            for method in df_summary["method"].unique():
                sub_df = df_summary[df_summary["method"] == method]
                color = palette.get(method, "#7f8c8d")
                marker = markers.get(method, "o")
                lw = 2.8 if "0.94" in method or "0.96" in method or "Exact" in method else 1.8
                ax.plot(
                    sub_df["noise_level_pct"],
                    sub_df[metric],
                    label=method,
                    color=color,
                    marker=marker,
                    linewidth=lw,
                    markersize=7
                )

            ax.set_title(titles[i], fontweight="bold", pad=12)
            ax.set_xlabel("Typographical Noise Level (%)", fontweight="bold")
            ax.set_xticks(self.noise_levels)
            ax.set_ylim(-0.05, 1.05)
            if i == 0:
                ax.set_ylabel("Metric Score [0.0 - 1.0]", fontweight="bold")
            if i == 2:
                ax.legend(loc="upper right", frameon=True, fontsize=9)

        plt.tight_layout()

        # Save figures
        png_path = os.path.join(Config.FIGURES_DIR, "rq1_accuracy_vs_noise.png")
        pdf_path = os.path.join(Config.FIGURES_DIR, "rq1_accuracy_vs_noise.pdf")
        plt.savefig(png_path, dpi=300, bbox_inches="tight")
        plt.savefig(pdf_path, bbox_inches="tight")
        plt.close()

        logger.info(f"Publication figures saved -> {png_path} and {pdf_path}")

    def plot_threshold_sensitivity(self, df_summary: pd.DataFrame):
        """
        Plots Threshold Sensitivity Curves: Precision, Recall, and F1 as a function of threshold tau.
        """
        fuzzy_df = df_summary[df_summary["method"] != "Baseline (Exact Matching)"].copy()
        if fuzzy_df.empty:
            return

        _, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
        noise_targets = [0, 5]
        titles = ["(a) Threshold Sensitivity at 0% Noise (Clean)", "(b) Threshold Sensitivity at 5% Noise"]

        for idx, noise in enumerate(noise_targets):
            ax = axes[idx]
            sub = fuzzy_df[fuzzy_df["noise_level_pct"] == noise].sort_values("threshold")
            ax.plot(sub["threshold"], sub["precision"], marker="o", color="#2ecc71", linewidth=2.5, label="Precision")
            ax.plot(sub["threshold"], sub["recall"], marker="s", color="#3498db", linewidth=2.5, label="Recall")
            ax.plot(sub["threshold"], sub["f1_score"], marker="^", color="#e74c3c", linewidth=2.5, label="F1-Score")

            ax.set_title(titles[idx], fontweight="bold", pad=12)
            ax.set_xlabel("Similarity Threshold (tau)", fontweight="bold")
            ax.set_xticks(self.thresholds)
            ax.set_ylim(-0.05, 1.05)
            if idx == 0:
                ax.set_ylabel("Metric Score [0.0 - 1.0]", fontweight="bold")
            ax.legend(loc="best", frameon=True)

        plt.tight_layout()
        sens_png = os.path.join(Config.FIGURES_DIR, "rq1_threshold_sensitivity.png")
        sens_pdf = os.path.join(Config.FIGURES_DIR, "rq1_threshold_sensitivity.pdf")
        plt.savefig(sens_png, dpi=300, bbox_inches="tight")
        plt.savefig(sens_pdf, bbox_inches="tight")
        plt.close()
        logger.info(f"Sensitivity figures saved -> {sens_png} and {sens_pdf}")


if __name__ == "__main__":
    runner = Experiment1AccuracyBenchmark()
    summary_df = runner.execute_benchmark()
    runner.plot_results(summary_df)
    runner.plot_threshold_sensitivity(summary_df)

    print("\n========================= RQ1 ACCURACY SUMMARY =========================")
    print(summary_df[["method", "threshold", "noise_level_pct", "precision", "recall", "f1_score"]].to_string(index=False))