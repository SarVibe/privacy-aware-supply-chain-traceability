"""
experiments/exp1_accuracy_benchmark.py
Component 1: Experimental Evaluation Engine  (revised, v3)

Role:
- Executes Research Question 1 (RQ1): Linkage Accuracy Benchmark under Typographical Noise.
- Compares the proposed Keyed Bloom Filter fuzzy matching (Algorithm 1) against SHA-256 exact matching.
- Noise levels: 0%, 5%, 15%, 30%.
- 2x2 design: {Exact SHA-256, Keyed BF} x {description-only, composite fields}.

Two noise models (--noise-model):
  all_records  (default, worst case): noise x% = char-level mutation rate applied to EVERY record's
               description (max(1, round(x% * len)) operations). Exact matching collapses to ~0 immediately.
  record_level (realistic):           noise x% = probability that a record is corrupted at all; a corrupted
               record gets a fixed char-level mutation intensity (--record-char-pct, default 5%), the other
               records stay clean. Exact matching then degrades gradually.

Threshold (tau) policies reported in the headline table:
  tuned       : ONE global tau selected on the tuning seeds (max mean F1 over all noise levels).
  default     : Config.DEFAULT_SIMILARITY_THRESHOLD (shows what happens if the config default is used).
  noise-aware : one tau PER noise level, selected on the tuning seeds (leak-free).
  oracle      : best tau per noise level chosen on the reporting seeds themselves (UPPER BOUND only).

Usage:
    python -m experiments.rq1.run_grid
    python -m experiments.rq1.run_grid --noise-model record_level
    python -m experiments.rq1.run_grid --tuning-seeds 42 43 44 45 46 --reporting-seeds 47 48 49 50 51 52 53 54 55 56
    python -m experiments.rq1.run_grid --seeds 1          # smoke test (tuning == reporting, leaky)
"""

import os
import tempfile
# Redirect matplotlib cache to writable temp directory to avoid Windows permission latency
os.environ["MPLCONFIGDIR"] = os.path.join(tempfile.gettempdir(), "matplotlib_c1_cache")

import argparse
import logging
import random
import string
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Headless visualization
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import wilcoxon

from src.config import Config
from src.rq1.exact_matcher import ExactMatcher
from src.common.preprocessor import TextPreprocessor
from src.common.keyed_bloom_filter import KeyedBloomFilter
from src.rq1.entity_resolver import EntityResolver
from src.rq2.metrics import LinkageMetrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------
# Method names (single source of truth, used by tables and plots)
# --------------------------------------------------------------------------------------
M_EXACT_RAW = "Exact SHA-256, raw (description)"          # ablation: no normalization
M_EXACT_DESC = "Exact SHA-256 (description)"
M_EXACT_COMP = "Exact SHA-256 (composite)"
M_BF_DESC = "Keyed BF (description)"
M_BF_COMP = "Keyed BF (composite)"

EXACT_METHODS = [M_EXACT_RAW, M_EXACT_DESC, M_EXACT_COMP]
BF_METHODS = [M_BF_DESC, M_BF_COMP]
METRICS = ["precision", "recall", "f1_score"]
METRIC_TITLES = {"precision": "(a) Pairwise Precision",
                 "recall": "(b) Pairwise Recall",
                 "f1_score": "(c) Pairwise F1-Score"}

# tau policies
P_NONE = "—"
P_TUNED = "tuned (global)"
P_DEFAULT = "default (Config)"
P_NOISE_AWARE = "noise-aware (tuned per noise)"
P_ORACLE = "oracle (upper bound)"

BASE_SEED = 42  # matches the default seed in Config / noise_generator
NOISE_MODELS = ("all_records", "record_level")


class Experiment1AccuracyBenchmark:
    """
    Executes and visualizes the RQ1 Linkage Accuracy Benchmark across noise levels,
    seeds, methods and thresholds.
    """

    def __init__(
        self,
        thresholds: Optional[List[float]] = None,
        main_threshold: Optional[float] = None,
        n_seeds: int = 10,
        noise_source: str = "inline",
        include_raw_ablation: bool = True,
        seeds: Optional[List[int]] = None,
        data_dir: Optional[str] = None,
        output_suffix: str = "",
        noise_model: str = "all_records",
        record_char_pct: int = 5,
    ):
        Config.ensure_directories()
        if noise_model not in NOISE_MODELS:
            raise ValueError(f"noise_model must be one of {NOISE_MODELS}")
        if noise_model == "record_level" and record_char_pct <= 0:
            raise ValueError("record_char_pct must be > 0 for the record_level noise model")

        self.noise_levels = list(Config.RQ1_NOISE_LEVELS)  # [0, 5, 15, 30]
        self.thresholds = thresholds or [
            0.50, 0.55, 0.60, 0.65, 0.70, 0.75,
            0.80, 0.85, 0.90, 0.92, 0.94, 0.96,
        ]
        self.default_tau = float(Config.DEFAULT_SIMILARITY_THRESHOLD)
        self.main_tau = main_threshold if main_threshold is not None else self.default_tau
        for tau in (self.main_tau, self.default_tau):
            if not any(np.isclose(tau, t) for t in self.thresholds):
                self.thresholds = sorted(self.thresholds + [tau])

        self.seeds = list(seeds) if seeds is not None else [BASE_SEED + i for i in range(n_seeds)]
        self.noise_source = noise_source
        self.data_dir = data_dir or str(Config.DATA_GENERATED_DIR)
        self.noise_model = noise_model
        self.record_char_pct = int(record_char_pct)
        # never overwrite the all_records results when running the record_level variant
        if noise_model == "record_level" and not output_suffix:
            output_suffix = "_record_level"
        self.output_suffix = output_suffix

        # per-noise tau selected on tuning seeds: {method: {noise: tau}}
        self.noise_aware_tau: Dict[str, Dict[int, float]] = {}

        self.exact_matcher = ExactMatcher()  # normalized SHA-256 (default behaviour)
        self.raw_matcher = None
        if include_raw_ablation:
            try:
                self.raw_matcher = ExactMatcher(normalize=False)
            except TypeError:
                logger.warning("ExactMatcher has no 'normalize' argument -> raw SHA-256 ablation skipped.")

        self.bf_engine = KeyedBloomFilter(
            length=Config.DEFAULT_BF_LENGTH,
            num_hashes=Config.DEFAULT_NUM_HASHES,
        )
        self._base_df: Optional[pd.DataFrame] = None

    def _result_name(self, stem: str, extension: str = "") -> str:
        return f"{stem}{self.output_suffix}{extension}"

    def _noise_axis_label(self) -> str:
        if self.noise_model == "record_level":
            return f"% of records corrupted (each with {self.record_char_pct}% char mutation)"
        return "Typographical noise level (% char mutation, every record)"

    # ------------------------------------------------------------------ data
    def _load_base_dataset(self) -> pd.DataFrame:
        """The 0%-noise dataset is the clean master from which noisy variants are derived."""
        if self._base_df is None:
            path = os.path.join(self.data_dir, f"noisy_products_0_seed{BASE_SEED}.csv")
            if not os.path.exists(path):
                path = os.path.join(self.data_dir, "noisy_products_0.csv")
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"Missing dataset {path}. Run 'python -m experiments.rq1.noise_generator' first."
                )
            self._base_df = pd.read_csv(path)
        return self._base_df.copy()

    def _load_clean(self, seed: int) -> pd.DataFrame:
        """Clean (0% noise) records for a seed."""
        if self.noise_source == "files":
            seeded = os.path.join(self.data_dir, f"noisy_products_0_seed{seed}.csv")
            if os.path.exists(seeded):
                return pd.read_csv(seeded)
        return self._load_base_dataset()

    @staticmethod
    def _inject_noise(text: str, rate: float, rng: random.Random) -> str:
        """
        Character-level mutation (substitution / deletion / insertion / transposition).
        Number of operations = max(1, round(rate * len(text))), mirroring the dataset generator.
        Applied to the description field ONLY.
        """
        if not isinstance(text, str) or not text or rate <= 0:
            return text
        chars = list(text)
        alphabet = string.ascii_lowercase + string.digits
        n_ops = max(1, int(round(rate * len(chars))))
        for _ in range(n_ops):
            if not chars:
                break
            op = rng.choice(("sub", "del", "ins", "swap"))
            pos = rng.randrange(len(chars))
            if op == "sub":
                chars[pos] = rng.choice(alphabet)
            elif op == "del":
                del chars[pos]
            elif op == "ins":
                chars.insert(pos, rng.choice(alphabet))
            elif pos < len(chars) - 1:  # swap
                chars[pos], chars[pos + 1] = chars[pos + 1], chars[pos]
        return "".join(chars)

    def _load_noisy_all_records(self, noise_pct: int, seed: int) -> pd.DataFrame:
        """Dataset where EVERY description has been mutated at the given char-level rate."""
        if self.noise_source == "files":
            seeded = os.path.join(self.data_dir, f"noisy_products_{noise_pct}_seed{seed}.csv")
            legacy = os.path.join(self.data_dir, f"noisy_products_{noise_pct}.csv")
            if os.path.exists(seeded):
                return pd.read_csv(seeded)
            if seed == BASE_SEED and os.path.exists(legacy):
                return pd.read_csv(legacy)
            raise FileNotFoundError(
                f"No dataset for noise={noise_pct}, seed={seed}. Generate it with your noise_generator "
                f"(seed={seed}) as '{os.path.basename(seeded)}', or use --noise-source inline."
            )
        # inline: derive from clean master with a deterministic per-(seed, noise) RNG
        df = self._load_base_dataset()
        if noise_pct > 0:
            rng = random.Random(seed * 1000 + noise_pct)
            rate = noise_pct / 100.0
            df["raw_item_description"] = [
                self._inject_noise(t, rate, rng) for t in df["raw_item_description"]
            ]
        return df

    def _get_dataset(self, noise_pct: int, seed: int) -> pd.DataFrame:
        """
        Returns the dataset for (noise level, seed) with a 'composite_text' column added.
        all_records : every description mutated at noise_pct% char rate.
        record_level: each record corrupted with probability noise_pct% (char rate = record_char_pct%).
        """
        if self.noise_model == "all_records" or noise_pct == 0:
            df = self._load_noisy_all_records(noise_pct, seed)
        else:
            df = self._load_clean(seed)
            noisy = self._load_noisy_all_records(self.record_char_pct, seed)
            noisy_map = dict(zip(noisy["record_id"].astype(str), noisy["raw_item_description"]))
            rng = random.Random(seed * 1000 + noise_pct + 17)
            p = noise_pct / 100.0
            corrupt = [rng.random() < p for _ in range(len(df))]
            ids = df["record_id"].astype(str)
            df["raw_item_description"] = [
                noisy_map.get(rid, desc) if flag else desc
                for rid, desc, flag in zip(ids, df["raw_item_description"], corrupt)
            ]

        # Composite text for the exact baseline: description + the SAME structured fields the BF sees.
        for col in ("dosage", "dosage_form", "pack_size"):
            if col not in df.columns:
                df[col] = ""
        df["composite_text"] = (
            df["raw_item_description"].fillna("").astype(str) + " "
            + df["dosage"].fillna("").astype(str) + " "
            + df["dosage_form"].fillna("").astype(str) + " "
            + df["pack_size"].fillna("").astype(str)
        )
        return df

    # ------------------------------------------------------------- baselines
    @staticmethod
    def _run_exact(matcher: ExactMatcher, df: pd.DataFrame, text_column: str) -> dict:
        matcher.reset()
        df_res = matcher.process_dataset(df, text_column=text_column, id_column="record_id")
        return LinkageMetrics.compute_pairwise_metrics(df_res)

    # -------------------------------------------------------------- proposed
    def _encode_records(self, df: pd.DataFrame, use_structured: bool) -> List[dict]:
        """
        Encodes every record into a keyed Bloom filter once.
        use_structured=True  -> Tag(Name) U Tag(Dosage) U Tag(Form) U Tag(Pack)   (composite)
        use_structured=False -> Tag(Name) only                                    (description-only)
        """
        records = []
        for _, row in df.iterrows():
            raw_description = row["raw_item_description"]
            qgrams = TextPreprocessor.extract_composite_qgrams(
                text=raw_description if pd.notna(raw_description) else "",
                dosage=row.get("dosage", None) if use_structured else None,
                dosage_form=row.get("dosage_form", None) if use_structured else None,
                pack_size=row.get("pack_size", None) if use_structured else None,
                q=Config.DEFAULT_Q,
            )
            records.append({
                "record_id": str(row["record_id"]),
                "true_entity_id": str(row["true_entity_id"]),
                "bloom_filter": self.bf_engine.encode(qgrams),
            })
        return records

    @staticmethod
    def _run_resolver(records: List[dict], threshold: float) -> dict:
        resolver = EntityResolver(threshold=threshold)
        df_res = resolver.process_dataset(records)
        return LinkageMetrics.compute_pairwise_metrics(df_res)

    # ------------------------------------------------------------- benchmark
    @staticmethod
    def _row(seed, noise, method, threshold, m) -> dict:
        return {
            "seed": seed, "noise_level_pct": noise, "method": method, "threshold": threshold,
            "precision": m["precision"], "recall": m["recall"], "f1_score": m["f1_score"],
            "tp": m["tp"], "fp": m["fp"], "fn": m["fn"],
        }

    def execute_benchmark(self, raw_stem: str = "rq1_accuracy_benchmark_raw_per_seed") -> pd.DataFrame:
        """Runs all methods x noise levels x seeds x thresholds. Returns the raw per-seed table."""
        rows = []
        logger.info("=" * 70)
        logger.info("RQ1 Accuracy Benchmark | seeds=%s | noise source=%s | noise model=%s",
                    self.seeds, self.noise_source, self.noise_model)
        logger.info("Headline tau = %.2f | default tau = %.2f | sweep taus = %s",
                    self.main_tau, self.default_tau, self.thresholds)
        logger.info("=" * 70)

        for seed in self.seeds:
            for noise in self.noise_levels:
                logger.info("seed=%d | noise=%d%%", seed, noise)
                df = self._get_dataset(noise, seed)

                # ---- Exact SHA-256 baselines (order independent) ----
                if self.raw_matcher is not None:
                    rows.append(self._row(seed, noise, M_EXACT_RAW, np.nan,
                                          self._run_exact(self.raw_matcher, df, "raw_item_description")))
                rows.append(self._row(seed, noise, M_EXACT_DESC, np.nan,
                                      self._run_exact(self.exact_matcher, df, "raw_item_description")))
                rows.append(self._row(seed, noise, M_EXACT_COMP, np.nan,
                                      self._run_exact(self.exact_matcher, df, "composite_text")))

                # ---- Keyed BF (encode once, sweep thresholds) ----
                for method, structured in ((M_BF_DESC, False), (M_BF_COMP, True)):
                    records = self._encode_records(df, use_structured=structured)
                    # Greedy leader-based clustering is order dependent -> shuffle per seed
                    shuffled = records[:]
                    random.Random(seed).shuffle(shuffled)
                    for tau in self.thresholds:
                        rows.append(self._row(seed, noise, method, tau,
                                              self._run_resolver(shuffled, tau)))

        df_raw = pd.DataFrame(rows)
        raw_csv = os.path.join(Config.RQ1_RAW_DIR, self._result_name(raw_stem, ".csv"))
        df_raw.to_csv(raw_csv, index=False)
        logger.info("Saved per-seed results -> %s", raw_csv)
        return df_raw

    # ---------------------------------------------------- tau selection (tuning seeds only)
    @staticmethod
    def select_threshold(df_tuning: pd.DataFrame) -> float:
        """Global tau: max mean F1 (over seeds AND noise levels) of composite BF on the tuning seeds."""
        tuning = df_tuning[
            (df_tuning["method"] == M_BF_COMP) & df_tuning["threshold"].notna()
        ]
        if tuning.empty:
            raise ValueError("Threshold tuning requires composite BF sweep results.")
        scores = tuning.groupby("threshold")["f1_score"].mean()
        return float(scores.idxmax())

    @staticmethod
    def select_threshold_per_noise(df_tuning: pd.DataFrame, method: str) -> Dict[int, float]:
        """Noise-aware tau: for each noise level, tau with max mean F1 on the tuning seeds."""
        sub = df_tuning[(df_tuning["method"] == method) & df_tuning["threshold"].notna()]
        if sub.empty:
            return {}
        scores = sub.groupby(["noise_level_pct", "threshold"])["f1_score"].mean().reset_index()
        best = scores.loc[scores.groupby("noise_level_pct")["f1_score"].idxmax()]
        return {int(n): float(t) for n, t in zip(best["noise_level_pct"], best["threshold"])}

    def save_tau_policies(self) -> pd.DataFrame:
        rows = [
            {"policy": P_TUNED, "method": M_BF_COMP, "noise_level_pct": "all", "tau": self.main_tau},
            {"policy": P_DEFAULT, "method": "all BF", "noise_level_pct": "all", "tau": self.default_tau},
        ]
        for method, mapping in self.noise_aware_tau.items():
            for noise, tau in sorted(mapping.items()):
                rows.append({"policy": P_NOISE_AWARE, "method": method,
                             "noise_level_pct": noise, "tau": tau})
        df = pd.DataFrame(rows)
        df.to_csv(os.path.join(Config.RQ1_TABLES_DIR, self._result_name("rq1_tau_policies", ".csv")), index=False)
        return df

    # ----------------------------------------------------------- statistics
    def statistical_comparison(self, df_raw: pd.DataFrame) -> pd.DataFrame:
        """
        Paired Wilcoxon tests across reporting seeds for the two FAIR pairs
        (same input information on both sides), BF at the tuned global tau.
        """
        pairs = ((M_BF_COMP, M_EXACT_COMP), (M_BF_DESC, M_EXACT_DESC))
        rows = []
        for bf_method, exact_method in pairs:
            for noise in self.noise_levels:
                exact = df_raw[
                    (df_raw["method"] == exact_method) & (df_raw["noise_level_pct"] == noise)
                ].set_index("seed")
                bf = df_raw[
                    (df_raw["method"] == bf_method)
                    & (df_raw["noise_level_pct"] == noise)
                    & np.isclose(df_raw["threshold"], self.main_tau)
                ].set_index("seed")
                paired = exact[METRICS].join(bf[METRICS], lsuffix="_exact", rsuffix="_bf", how="inner")
                n = len(paired)
                min_p = (2.0 / 2 ** n) if n > 0 else np.nan
                for metric in METRICS:
                    diff = paired[f"{metric}_bf"] - paired[f"{metric}_exact"]
                    if n < 2 or np.allclose(diff, 0):
                        statistic, p_value = 0.0, 1.0
                    else:
                        try:
                            res = wilcoxon(paired[f"{metric}_bf"], paired[f"{metric}_exact"],
                                           zero_method="wilcox", alternative="two-sided")
                            statistic, p_value = float(res.statistic), float(res.pvalue)
                        except ValueError:
                            statistic, p_value = np.nan, np.nan
                    rows.append({
                        "noise_level_pct": noise,
                        "metric": metric,
                        "comparison": f"{bf_method} vs {exact_method}",
                        "tau": self.main_tau,
                        "n_pairs": n,
                        "mean_diff_bf_minus_exact": float(diff.mean()) if n else np.nan,
                        "wilcoxon_statistic": statistic,
                        "p_value": p_value,
                        "min_attainable_p": min_p,
                    })
        result_df = pd.DataFrame(rows)
        if not result_df.empty and (result_df["min_attainable_p"] > 0.05).any():
            logger.warning(
                "Only %d reporting seeds: the smallest attainable two-sided Wilcoxon p-value is %.4f (> 0.05). "
                "Use >= 6 reporting seeds (10 recommended) for significance to be attainable.",
                int(result_df["n_pairs"].min()), float(result_df["min_attainable_p"].max()),
            )
        result_df.to_csv(
            os.path.join(Config.RQ1_TABLES_DIR, self._result_name("rq1_wilcoxon_comparisons", ".csv")), index=False
        )
        return result_df

    def entity_bootstrap_comparison(self, n_bootstrap: int = 200) -> pd.DataFrame:
        """Entity-level bootstrap 95% CIs for the four fair-pair methods on the reporting seeds."""
        specs = (
            (M_EXACT_DESC, "exact", "raw_item_description"),
            (M_EXACT_COMP, "exact", "composite_text"),
            (M_BF_DESC, "bf", False),
            (M_BF_COMP, "bf", True),
        )
        rows = []
        for noise in self.noise_levels:
            for seed in self.seeds:
                df = self._get_dataset(noise, seed)
                for method, kind, arg in specs:
                    if kind == "exact":
                        matcher = ExactMatcher()
                        matcher.reset()
                        result = matcher.process_dataset(df, text_column=arg, id_column="record_id")
                    else:
                        records = self._encode_records(df, use_structured=arg)
                        random.Random(seed).shuffle(records)
                        result = EntityResolver(threshold=self.main_tau).process_dataset(records)
                    interval = LinkageMetrics.entity_bootstrap_ci(
                        result, n_bootstrap=n_bootstrap, random_seed=seed
                    )
                    rows.append({"noise_level_pct": noise, "method": method, "seed": seed, **interval})
        result_df = pd.DataFrame(rows)
        result_df.to_csv(
            os.path.join(Config.RQ1_TABLES_DIR, self._result_name("rq1_entity_bootstrap_ci", ".csv")),
            index=False,
        )
        return result_df

    # ----------------------------------------------------------- aggregation
    def aggregate(self, df_raw: pd.DataFrame) -> pd.DataFrame:
        """mean / std over seeds for every (method, threshold, noise)."""
        agg = (
            df_raw.groupby(["method", "threshold", "noise_level_pct"], dropna=False)
            .agg(
                precision_mean=("precision", "mean"), precision_std=("precision", "std"),
                recall_mean=("recall", "mean"), recall_std=("recall", "std"),
                f1_score_mean=("f1_score", "mean"), f1_score_std=("f1_score", "std"),
                tp_mean=("tp", "mean"), fp_mean=("fp", "mean"), fn_mean=("fn", "mean"),
                n_seeds=("seed", "nunique"),
            )
            .reset_index()
            .fillna({"precision_std": 0.0, "recall_std": 0.0, "f1_score_std": 0.0})
        )
        out = os.path.join(
            Config.RQ1_TABLES_DIR, self._result_name("rq1_accuracy_benchmark_aggregated", ".csv")
        )
        agg.to_csv(out, index=False)
        logger.info("Saved aggregated results -> %s", out)
        return agg

    # ------------------------------------------------- headline / tau policies
    def _bf_policy_rows(self, agg: pd.DataFrame, method: str, policy: str) -> pd.DataFrame:
        """Rows of the aggregated table that correspond to a BF method under a tau policy."""
        sub = agg[(agg["method"] == method) & agg["threshold"].notna()]
        if sub.empty:
            return sub.copy()
        if policy == P_TUNED:
            out = sub[np.isclose(sub["threshold"], self.main_tau)]
        elif policy == P_DEFAULT:
            out = sub[np.isclose(sub["threshold"], self.default_tau)]
        elif policy == P_NOISE_AWARE:
            parts = []
            for noise, tau in self.noise_aware_tau.get(method, {}).items():
                parts.append(sub[(sub["noise_level_pct"] == noise) & np.isclose(sub["threshold"], tau)])
            out = pd.concat(parts) if parts else sub.iloc[0:0]
        elif policy == P_ORACLE:
            out = sub.loc[sub.groupby("noise_level_pct")["f1_score_mean"].idxmax()]
        else:
            raise ValueError(policy)
        return out.copy()

    def _headline_long(self, agg: pd.DataFrame) -> pd.DataFrame:
        """Long table of every (series, noise) row used by the headline table and plots."""
        spec = [
            (M_EXACT_RAW, None), (M_EXACT_DESC, None),
            (M_BF_DESC, P_TUNED),
            (M_EXACT_COMP, None),
            (M_BF_COMP, P_TUNED), (M_BF_COMP, P_DEFAULT),
            (M_BF_COMP, P_NOISE_AWARE), (M_BF_COMP, P_ORACLE),
        ]
        frames = []
        for method, policy in spec:
            if policy is None:
                part = agg[agg["method"] == method].copy()
                policy_name = P_NONE
            else:
                if policy == P_DEFAULT and np.isclose(self.main_tau, self.default_tau):
                    continue  # identical to the tuned row
                if policy == P_NOISE_AWARE and not self.noise_aware_tau:
                    continue
                part = self._bf_policy_rows(agg, method, policy)
                policy_name = policy
            if part.empty:
                continue
            part["policy"] = policy_name
            part["tau"] = part["threshold"]
            if policy_name == P_NONE:
                part["series"] = method
            elif policy_name == P_TUNED:
                part["series"] = f"{method} [tuned τ={self.main_tau:.2f}]"
            elif policy_name == P_DEFAULT:
                part["series"] = f"{method} [default τ={self.default_tau:.2f}]"
            elif policy_name == P_NOISE_AWARE:
                part["series"] = f"{method} [noise-aware τ]"
            else:
                part["series"] = f"{method} [oracle τ, upper bound]"
            frames.append(part)
        long = pd.concat(frames, ignore_index=True)
        order = list(dict.fromkeys(long["series"]))
        long["rank"] = long["series"].map({s: i for i, s in enumerate(order)})
        return long.sort_values(["noise_level_pct", "rank"]).reset_index(drop=True)

    @staticmethod
    def _fmt(mean, std) -> str:
        return f"{mean:.3f} ± {std:.3f}"

    @staticmethod
    def _latex_fix(latex: str) -> str:
        return (latex.replace("%", "\\%").replace("±", "$\\pm$")
                .replace("τ", "$\\tau$").replace("—", "--"))

    def headline_table(self, agg: pd.DataFrame) -> pd.DataFrame:
        """
        Headline RQ1 table: exact baselines + Keyed BF under several tau policies
        (tuned global, config default, noise-aware, oracle upper bound).
        """
        long = self._headline_long(agg)
        pretty = pd.DataFrame({
            "Noise (%)": long["noise_level_pct"],
            "Method": long["method"],
            "τ policy": long["policy"],
            "τ": [f"{t:.2f}" if pd.notna(t) else "—" for t in long["tau"]],
            "Precision": [self._fmt(a, b) for a, b in zip(long["precision_mean"], long["precision_std"])],
            "Recall": [self._fmt(a, b) for a, b in zip(long["recall_mean"], long["recall_std"])],
            "F1": [self._fmt(a, b) for a, b in zip(long["f1_score_mean"], long["f1_score_std"])],
        })
        pretty.to_csv(
            os.path.join(Config.RQ1_TABLES_DIR, self._result_name("rq1_headline_table", ".csv")), index=False
        )
        caption = (f"RQ1 linkage accuracy, noise model: {self.noise_model.replace('_', ' ')} "
                   f"(mean $\\pm$ std over {len(self.seeds)} reporting seeds). "
                   f"Oracle rows select $\\tau$ on the reporting seeds and are an upper bound.")
        latex = self._latex_fix(
            pretty.to_latex(index=False, escape=False, caption=caption, label="tab:rq1_headline")
        )
        with open(
            os.path.join(Config.RQ1_TABLES_DIR, self._result_name("rq1_headline_table", ".tex")),
            "w", encoding="utf-8"
        ) as fh:
            fh.write(latex)
        logger.info("Saved headline table (CSV + LaTeX) in %s", Config.RQ1_TABLES_DIR)
        return pretty

    def oracle_threshold_table(self, agg: pd.DataFrame) -> pd.DataFrame:
        """
        Per-noise best tau (oracle, UPPER BOUND: selected on the reporting seeds) for both BF variants,
        shown next to the tuned-global and default-tau F1 so the cost of a fixed tau is visible.
        """
        rows = []
        for method in BF_METHODS:
            sub = agg[(agg["method"] == method) & agg["threshold"].notna()]
            if sub.empty:
                continue
            for noise in self.noise_levels:
                s = sub[sub["noise_level_pct"] == noise]
                best = s.loc[s["f1_score_mean"].idxmax()]
                tuned = s[np.isclose(s["threshold"], self.main_tau)]
                dflt = s[np.isclose(s["threshold"], self.default_tau)]
                rows.append({
                    "Noise (%)": noise,
                    "Method": method,
                    "oracle τ*": f"{best['threshold']:.2f}",
                    "Precision": self._fmt(best["precision_mean"], best["precision_std"]),
                    "Recall": self._fmt(best["recall_mean"], best["recall_std"]),
                    "F1 (oracle)": self._fmt(best["f1_score_mean"], best["f1_score_std"]),
                    f"F1 (tuned τ={self.main_tau:.2f})":
                        f"{tuned['f1_score_mean'].iloc[0]:.3f}" if not tuned.empty else "n/a",
                    f"F1 (default τ={self.default_tau:.2f})":
                        f"{dflt['f1_score_mean'].iloc[0]:.3f}" if not dflt.empty else "n/a",
                })
        table = pd.DataFrame(rows)
        table.to_csv(
            os.path.join(Config.RQ1_TABLES_DIR, self._result_name("rq1_oracle_threshold_table", ".csv")), index=False
        )
        latex = self._latex_fix(table.to_latex(
            index=False, escape=False, label="tab:rq1_oracle_tau",
            caption="Per-noise oracle threshold (upper bound; $\\tau$ chosen on the reporting seeds) "
                    "versus the tuned global and the default threshold.",
        ))
        with open(
            os.path.join(Config.RQ1_TABLES_DIR, self._result_name("rq1_oracle_threshold_table", ".tex")),
            "w", encoding="utf-8"
        ) as fh:
            fh.write(latex)
        return table

    # ------------------------------------------------------------------ plots
    @staticmethod
    def _style_for(series_info: pd.DataFrame) -> Dict[str, dict]:
        palette = sns.color_palette("colorblind", n_colors=len(series_info))
        markers = ["o", "s", "^", "D", "P", "X", "v", "<"]
        linestyles = {P_NONE: "--", P_TUNED: "-", P_DEFAULT: ":", P_NOISE_AWARE: "-."}
        styles = {}
        for i, (_, r) in enumerate(series_info.iterrows()):
            styles[r["series"]] = {
                "color": palette[i],
                "marker": markers[i % len(markers)],
                "linestyle": linestyles.get(r["policy"], "-"),
            }
        return styles

    def plot_headline(self, agg: pd.DataFrame):
        """
        Accuracy vs noise: exact baselines vs Keyed BF under the tuned / default / noise-aware tau
        (oracle and raw-SHA ablation are in the tables only), with std error bars.
        """
        sns.set_theme(style="whitegrid", font_scale=1.1)
        long = self._headline_long(agg)
        long = long[(long["policy"] != P_ORACLE) & (long["method"] != M_EXACT_RAW)]
        series_info = long[["series", "method", "policy"]].drop_duplicates().reset_index(drop=True)
        styles = self._style_for(series_info)

        _, axes = plt.subplots(1, 3, figsize=(20, 6), sharey=True)
        for ax, metric in zip(axes, METRICS):
            for s in series_info["series"]:
                sub = long[long["series"] == s].sort_values("noise_level_pct")
                ax.errorbar(sub["noise_level_pct"], sub[f"{metric}_mean"], yerr=sub[f"{metric}_std"],
                            label=s, linewidth=2.0, markersize=7, capsize=3, **styles[s])
            ax.set_title(METRIC_TITLES[metric], fontweight="bold", pad=12)
            ax.set_xlabel(self._noise_axis_label(), fontweight="bold")
            ax.set_xticks(self.noise_levels)
            ax.set_ylim(-0.05, 1.05)
        axes[0].set_ylabel("Metric score (mean ± std over seeds)", fontweight="bold")
        axes[2].legend(loc="upper right", frameon=True, fontsize=8)
        plt.tight_layout()
        for ext, kw in (("png", {"dpi": 300}), ("pdf", {})):
            plt.savefig(os.path.join(
                            Config.RQ1_FIGURES_DIR, self._result_name("rq1_accuracy_vs_noise", f".{ext}")),
                        bbox_inches="tight", **kw)
        plt.close()
        logger.info("Saved headline figures -> %s", Config.RQ1_FIGURES_DIR)

    def plot_threshold_sensitivity(self, agg: pd.DataFrame):
        """
        Supplementary: P / R / F1 vs tau for the composite Keyed BF at the noisy levels
        (5, 15, 30%). Description-only F1 is a dashed grey line; solid black = tuned tau,
        dashed gray = default tau.
        """
        sens_noise = [n for n in self.noise_levels if n > 0]
        _, axes = plt.subplots(1, len(sens_noise), figsize=(6 * len(sens_noise), 5), sharey=True)
        axes = np.atleast_1d(axes)
        colors = {"precision": "#2ca02c", "recall": "#1f77b4", "f1_score": "#d62728"}
        markers = {"precision": "o", "recall": "s", "f1_score": "^"}

        for ax, noise in zip(axes, sens_noise):
            comp = agg[(agg["method"] == M_BF_COMP) & (agg["noise_level_pct"] == noise)].sort_values("threshold")
            for metric in METRICS:
                ax.plot(comp["threshold"], comp[f"{metric}_mean"], color=colors[metric],
                        marker=markers[metric], linewidth=2.3, label=metric.replace("_", " ").title())
                ax.fill_between(comp["threshold"],
                                comp[f"{metric}_mean"] - comp[f"{metric}_std"],
                                comp[f"{metric}_mean"] + comp[f"{metric}_std"],
                                color=colors[metric], alpha=0.15)
            desc = agg[(agg["method"] == M_BF_DESC) & (agg["noise_level_pct"] == noise)].sort_values("threshold")
            if not desc.empty:
                ax.plot(desc["threshold"], desc["f1_score_mean"], color="gray", linestyle="--",
                        linewidth=1.8, label="F1 (description-only)")
            ax.axvline(self.main_tau, color="black", linestyle=":", linewidth=1.3, label="tuned τ")
            if not np.isclose(self.main_tau, self.default_tau):
                ax.axvline(self.default_tau, color="gray", linestyle="-.", linewidth=1.3, label="default τ")
            ax.set_title(f"Threshold sensitivity at {noise}% noise", fontweight="bold", pad=12)
            ax.set_xlabel("Similarity Threshold (τ)", fontweight="bold")
            ax.set_xticks(self.thresholds)
            ax.tick_params(axis="x", labelrotation=60, labelsize=8)
            ax.set_ylim(-0.05, 1.05)
            ax.legend(loc="best", frameon=True, fontsize=8)
        axes[0].set_ylabel("Metric score (mean ± std)", fontweight="bold")
        plt.tight_layout()
        for ext, kw in (("png", {"dpi": 300}), ("pdf", {})):
            plt.savefig(os.path.join(
                            Config.RQ1_FIGURES_DIR, self._result_name("rq1_threshold_sensitivity", f".{ext}")),
                        bbox_inches="tight", **kw)
        plt.close()
        logger.info("Saved sensitivity figures -> %s", Config.RQ1_FIGURES_DIR)


def main():
    parser = argparse.ArgumentParser(description="RQ1 accuracy benchmark (Exact SHA-256 vs Keyed Bloom Filter)")
    parser.add_argument("--seeds", type=int, default=None,
                        help="legacy smoke test: N consecutive seeds, tuning == reporting (leaky)")
    parser.add_argument("--tuning-seeds", nargs="+", type=int, default=[42, 43, 44, 45, 46])
    parser.add_argument("--reporting-seeds", nargs="+", type=int, default=[47, 48, 49, 50, 51])
    parser.add_argument("--tau", type=float, default=None,
                        help="fixed headline threshold; omit to tune only on tuning seeds")
    parser.add_argument("--noise-source", choices=["inline", "files"], default="files",
                        help="files: read generator output; inline is retained for compatibility")
    parser.add_argument("--noise-model", choices=list(NOISE_MODELS), default="all_records",
                        help="all_records: every record mutated at x%% char rate; "
                             "record_level: x%% of records corrupted (fixed char rate)")
    parser.add_argument("--record-char-pct", type=int, default=5,
                        help="char-level mutation intensity of corrupted records (record_level model)")
    parser.add_argument("--data-dir", default=None, help="directory containing seeded noisy CSV files")
    parser.add_argument("--output-suffix", default="",
                        help="suffix for result files, e.g. _all_fields (record_level adds _record_level)")
    parser.add_argument("--bootstrap", type=int, default=200, help="entity-level bootstrap resamples")
    parser.add_argument("--no-bootstrap", action="store_true", help="skip the entity bootstrap CIs")
    parser.add_argument("--no-raw-ablation", action="store_true", help="skip the raw SHA-256 ablation")
    args = parser.parse_args()

    if args.seeds is not None:
        tuning_seeds = [BASE_SEED + i for i in range(args.seeds)]
        reporting_seeds = tuning_seeds
        logger.warning("--seeds uses the same seeds for tuning and reporting (leaky). Smoke test only.")
    else:
        tuning_seeds = args.tuning_seeds
        reporting_seeds = args.reporting_seeds
        if set(tuning_seeds) & set(reporting_seeds):
            logger.warning("Tuning and reporting seeds overlap -> tau selection leaks into the results.")

    common = dict(
        noise_source=args.noise_source,
        include_raw_ablation=not args.no_raw_ablation,
        data_dir=args.data_dir,
        output_suffix=args.output_suffix,
        noise_model=args.noise_model,
        record_char_pct=args.record_char_pct,
    )

    # ---- 1) tuning seeds: choose the global tau and the per-noise taus ----
    tuning_runner = Experiment1AccuracyBenchmark(main_threshold=args.tau, seeds=tuning_seeds, **common)
    tuning_raw = tuning_runner.execute_benchmark(raw_stem="rq1_threshold_tuning_raw_per_seed")
    selected_tau = args.tau if args.tau is not None else tuning_runner.select_threshold(tuning_raw)
    noise_aware = {m: tuning_runner.select_threshold_per_noise(tuning_raw, m) for m in BF_METHODS}

    # ---- 2) reporting seeds: evaluate with the frozen taus ----
    runner = Experiment1AccuracyBenchmark(main_threshold=selected_tau, seeds=reporting_seeds, **common)
    runner.noise_aware_tau = noise_aware
    df_raw = runner.execute_benchmark()
    agg = runner.aggregate(df_raw)
    head = runner.headline_table(agg)
    oracle = runner.oracle_threshold_table(agg)
    policies = runner.save_tau_policies()
    stats = runner.statistical_comparison(df_raw)
    if not args.no_bootstrap:
        runner.entity_bootstrap_comparison(n_bootstrap=args.bootstrap)
    runner.plot_headline(agg)
    runner.plot_threshold_sensitivity(agg)

    composite_sweep = agg[
        (agg["method"] == M_BF_COMP) & agg["threshold"].notna()
    ].sort_values(["noise_level_pct", "threshold"])
    print("\n====================== BF COMPOSITE TAU SWEEP ======================")
    print(composite_sweep[
        [
            "threshold", "noise_level_pct",
            "precision_mean", "recall_mean", "f1_score_mean",
            "tp_mean", "fp_mean", "fn_mean",
        ]
    ].to_string(index=False))

    print("\n====================== TAU POLICIES (selected on tuning seeds) ======================")
    print(policies.to_string(index=False))

    print("\n====================== ORACLE TAU PER NOISE (upper bound) ======================")
    print(oracle.to_string(index=False))

    print("\n====================== WILCOXON (fair pairs, tuned tau) ======================")
    print(stats[stats["metric"] == "f1_score"].to_string(index=False))

    print(f"\n====================== RQ1 HEADLINE | noise model = {args.noise_model} ======================")
    print(f"tuned tau = {runner.main_tau:.2f} | default tau = {runner.default_tau:.2f} | "
          f"tuning seeds = {tuning_seeds} | reporting seeds = {reporting_seeds}")
    print(head.to_string(index=False))


if __name__ == "__main__":
    main()