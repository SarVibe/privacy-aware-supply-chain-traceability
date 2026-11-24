"""Aggregate results -> tables, hypothesis tests (H1-H3), operating-point selection and figures.

  python -m experiments.rq2.results_analyzer --grid backend/app/results/rq2/raw/exp2_grid.csv [--dp backend/app/results/rq2/raw/exp2_dp.csv] [--noise 0.15]

Operating-point selection uses the first half of the seeds; the baseline comparison and the
Wilcoxon tests use the remaining seeds, so the 'tuned' configuration is not evaluated on the
data that selected it.
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from src.common.config import load_config
from src.common.evaluation.aggregation import (
    holm_adjust as holm_bonferroni,
    mean_ci95_half_width as ci95,
    paired_effect,
    paired_seed_differences as merge_paired,
)
from src.common.experiment.io import read_csv
from src.common.paths import results_dir
from src.common.experiment_metadata import (
    data_fingerprint,
    write_markdown,
    write_run_csv,
    parse_standard,
)
from src.rq2.results_schema import validate_results, SchemaError

BLUE, ORANGE, AQUA, INK, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e"
METRICS = ["precision", "recall", "f1", "fpr", "auc", "reid_top1", "reid_top5", "reid_ties", "reid_cands_delta",
           "reid_top1_conditional", "freq_success", "bit_success", "bit_baseline", "fill", "entropy", "load", "tau",
           "cross_party_f1", "cross_party_precision", "cross_party_recall", "cross_party_fpr",
           "f1_unc", "precision_unc", "recall_unc", "fpr_unc", "f1_01", "f1_05"]
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": "#e6e5e1",
                     "grid.linewidth": 0.6, "figure.dpi": 130})


def aggregate(df, keys):
    g = df.groupby(keys, dropna=False)
    present_metrics = [m for m in METRICS if m in df.columns]
    out = g[present_metrics].mean().add_suffix("_mean")
    out = out.join(g[present_metrics].std().add_suffix("_std")).join(g[present_metrics].agg(ci95).add_suffix("_ci95"))
    out["n_seeds"] = g["seed"].nunique()
    return out.reset_index()


def heatmap(ax, piv, title, fmt="{:.2f}", cmap="Blues", vmin=0, vmax=1, infeasible_mask=None):
    im = ax.imshow(piv.values, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(piv.shape[1])); ax.set_xticklabels(piv.columns)
    ax.set_yticks(range(piv.shape[0])); ax.set_yticklabels(piv.index)
    ax.set_xlabel("k (hash functions)"); ax.set_ylabel("l (filter length)"); ax.set_title(title, fontsize=10)
    ax.grid(False)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            is_infeasible = (infeasible_mask is not None and
                             not np.isnan(infeasible_mask.values[i, j]) and
                             infeasible_mask.values[i, j])
            if is_infeasible:
                rect = plt.Rectangle([j - 0.5, i - 0.5], 1, 1, fill=False, hatch="//", color=MUTED, linewidth=0)
                ax.add_patch(rect)
                ax.text(j, i, "infeasible\n@FPR≤0.01", ha="center", va="center", fontsize=6, color=MUTED)
            elif not np.isnan(v):
                dark = (v - vmin) / (vmax - vmin + 1e-12) > 0.6
                ax.text(j, i, fmt.format(v), ha="center", va="center", fontsize=8, color="white" if dark else INK)
    return im


def pareto_front(points):
    """points: list of (f1, top1, label); front = no other point has >= F1 and <= top1 (one strictly)."""
    front = []
    for f, t, lab in points:
        if not any((f2 >= f and t2 <= t) and (f2 > f or t2 < t) for f2, t2, _ in points):
            front.append((f, t, lab))
    return sorted(front)


def load_run_meta(csv_path: str) -> dict:
    csv_path = Path(csv_path)
    candidates = (
        csv_path.with_name(csv_path.stem + "_run_meta.json"),
        csv_path.with_name(csv_path.stem + "_meta.json"),
        csv_path.with_name("run_meta.json"),
    )
    meta_path = next((path for path in candidates if path.exists()), None)
    if meta_path is None:
        raise SystemExit(f"missing run metadata for {csv_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def validate_run_metas(meta_paths: list[tuple[str, dict]], degenerate_fill: float):
    required = ("q", "pad", "data_mode", "tau_grid", "degenerate_fill")
    reference_name, reference = meta_paths[0]
    ref_cfg = reference["experiment_config"]
    for name, meta in meta_paths:
        cfg = meta["experiment_config"]
        for key in required:
            if key not in cfg or cfg[key] != ref_cfg[key]:
                raise SystemExit(
                    f"run metadata mismatch for {key}: {reference_name}={ref_cfg[key]!r}, "
                    f"{name}={cfg.get(key)!r}"
                )
    if float(ref_cfg["degenerate_fill"]) != float(degenerate_fill):
        raise SystemExit(
            f"metadata degenerate_fill={ref_cfg['degenerate_fill']} does not match "
            f"configured threshold={degenerate_fill}"
        )


def main():
    cfg = load_config("rq2")
    sweep = cfg.sweep
    root = results_dir(cfg, "rq2")
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default=str(root / sweep.grid_csv))
    ap.add_argument("--dp", default=None)
    ap.add_argument("--overlap-csv", default=None, help="optional CSV from the E2.7 overlap run")
    ap.add_argument("--noise", type=float, default=sweep.analysis_noise, help="noise level used for the main analysis")
    ap.add_argument("--f1-min", type=float, default=sweep.min_f1, help="utility constraint for the operating point")
    ap.add_argument("--min-privacy-gain", type=float, default=sweep.min_privacy_gain,
                    help="minimum selected/standard median anonymity-set ratio")
    ap.add_argument("--n-selection", type=int, default=sweep.selection_seeds)
    ap.add_argument("--outdir", default=str(root / sweep.analysis_directory))
    ap.add_argument("--figures-dir", type=Path, help="output directory for figures (default: <outdir>/figures)")
    ap.add_argument("--standard", default=f"{cfg.bloom.l}:{cfg.bloom.k}", help="standard Bloom configuration as l:k")
    a = ap.parse_args()
    try:
        sl, sk = parse_standard(a.standard)
    except ValueError as exc:
        ap.error(str(exc))
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    figs = a.figures_dir if a.figures_dir is not None else out / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    metas = [("grid", load_run_meta(a.grid))]
    if a.dp:
        metas.append(("dp", load_run_meta(a.dp)))
    if a.overlap_csv:
        metas.append(("overlap", load_run_meta(a.overlap_csv)))
    degenerate_fill = float(metas[0][1]["experiment_config"]["degenerate_fill"])
    validate_run_metas(metas, degenerate_fill)

    df = read_csv(a.grid)
    source_runs = {
        "grid": {
            "path": str(Path(a.grid).resolve()),
            "sha256": data_fingerprint(a.grid)["sha256"],
        }
    }
    if a.overlap_csv:
        source_runs["overlap"] = {
            "path": str(Path(a.overlap_csv).resolve()),
            "sha256": data_fingerprint(a.overlap_csv)["sha256"],
        }
    analysis_scope = {
        "noise": float(a.noise),
        "overlap": sweep.overlap,
        "standard": [sl, sk],
        "tau_grid": list(metas[0][1]["experiment_config"]["tau_grid"]),
        "primary_metric": metas[0][1].get("analysis_scope", {}).get("primary_metric", "cross_party_pairs"),
    }
    try:
        validate_results(df)
    except SchemaError as exc:
        raise SystemExit(str(exc)) from exc
    available_noise = set(df["noise"].dropna().astype(float))
    if float(a.noise) not in available_noise:
        raise SystemExit(
            f"requested --noise {a.noise} is not present in CSV; available: {sorted(available_noise)}"
        )
    grid_configs = set(zip(df[df.method == "bloom"]["l"].astype(int), df[df.method == "bloom"]["k"].astype(int)))
    if (sl, sk) not in grid_configs:
        raise SystemExit(f"standard configuration {sl}:{sk} is not present in the grid")
    if "eps" in df.columns:
        df["eps"] = df["eps"].replace([np.inf], np.inf)
    main_df = df[df.overlap == sweep.overlap]

    # ---------- summary of everything ----------
    summary_keys = ["method", "l", "k", "noise"]
    if "eps" in main_df.columns:
        summary_keys.append("eps")
    summary = aggregate(main_df, summary_keys)
    write_run_csv(summary, out / "summary.csv",
                  q=metas[0][1]["experiment_config"]["q"],
                  pad=metas[0][1]["experiment_config"]["pad"],
                  data_mode=metas[0][1]["experiment_config"]["data_mode"],
                  source_runs=source_runs,
                  analysis_scope=analysis_scope)

    d = main_df[(main_df.noise == a.noise)]
    if d.empty:
        raise SystemExit(f"no rows with noise={a.noise}; available: {sorted(main_df.noise.unique())}")
    bf = d[d.method == "bloom"]
    ex = d[d.method == "exact_hash"]
    seeds = sorted(d.seed.unique())
    n_selection = min(max(1, a.n_selection), max(1, len(seeds) - 1))
    sel_seeds = seeds[:n_selection]
    eval_seeds = [s for s in seeds if s not in sel_seeds] or seeds
    if eval_seeds == seeds and len(seeds) > 1:
        print("WARNING: too few seeds to split selection/evaluation; using all seeds for both.")

    # ---------- operating-point selection (selection seeds only) ----------
    sel_f1_col = "f1"
    anon_col = "anonymity_set" if "anonymity_set" in bf.columns else None
    sel_grp_cols = [sel_f1_col, "fill"] + ([anon_col] if anon_col else [])
    sel = bf[bf.seed.isin(sel_seeds)].groupby(["l", "k"])[sel_grp_cols].mean().reset_index()
    cand = sel[sel.fill <= degenerate_fill]
    ok = cand[cand[sel_f1_col] >= a.f1_min]
    note = "" if not ok.empty else f"no config reached F1>={a.f1_min}"
    selected_config = None
    if not ok.empty:
        sort_cols = [anon_col, sel_f1_col, "fill"] if anon_col else [sel_f1_col, "fill"]
        tuned = ok.sort_values(sort_cols, ascending=[False, False, True]).iloc[0]
        tl, tk = int(tuned.l), int(tuned.k)
        selected_config = [tl, tk]
    else:
        tl, tk = sl, sk
    print(f"standard=({sl},{sk})  selected={selected_config}  {note}")

    # ---------- baseline comparison table (evaluation seeds) ----------
    ev = d[d.seed.isin(eval_seeds)]
    parts = {"exact_hash": ev[ev.method == "exact_hash"],
             f"standard_bf_l{sl}_k{sk}": ev[(ev.method == "bloom") & (ev.l == sl) & (ev.k == sk)],
             f"tuned_bf_l{tl}_k{tk}": ev[(ev.method == "bloom") & (ev.l == tl) & (ev.k == tk)]}
    cols = ["precision", "recall", "f1", "auc", "reid_top1", "reid_top1_conditional",
            "reid_top5", "reid_cands_delta", "freq_success", "bit_success", "bit_baseline", "fill", "entropy"]
    cols.extend(["cross_party_precision", "cross_party_recall", "cross_party_f1"])
    cols = [c for c in cols if c in ev.columns]
    rows = []
    for name, part in parts.items():
        r = {"setup": name, "n_seeds": part.seed.nunique()}
        for c in cols:
            r[c] = f"{part[c].mean():.3f} ± {ci95(part[c]):.3f}" if part[c].notna().any() else "n/a"
        rows.append(r)
    table = pd.DataFrame(rows)
    # Report A2 at noise zero, when repeated records of an entity retain the same token.
    z = main_df[(main_df.noise == 0.0) & main_df.seed.isin(eval_seeds)]
    if not z.empty:
        zsel = {"exact_hash": z[z.method == "exact_hash"],
                f"standard_bf_l{sl}_k{sk}": z[(z.method == "bloom") & (z.l == sl) & (z.k == sk)],
                f"tuned_bf_l{tl}_k{tk}": z[(z.method == "bloom") & (z.l == tl) & (z.k == tk)]}
        table["freq_success@noise0"] = [f"{zsel[n]['freq_success'].mean():.3f} ± {ci95(zsel[n]['freq_success']):.3f}"
                                         for n in table["setup"]]
    write_run_csv(table, out / "table_baselines.csv",
                  q=metas[0][1]["experiment_config"]["q"],
                  pad=metas[0][1]["experiment_config"]["pad"],
                  data_mode=metas[0][1]["experiment_config"]["data_mode"],
                  source_runs=source_runs,
                  analysis_scope=analysis_scope)
    # Rename columns with attack labels before writing the markdown (T6)
    table_md = table.rename(columns={
        "reid_top1": "reid_top1 [A1, insider, key known]",
        "reid_top1_conditional": "reid_top1_conditional [A1, insider, key known]",
        "reid_top5": "reid_top5 [A1, insider, key known]",
        "reid_cands_delta": "reid_cands_delta [A1, insider, key known]",
        "freq_success": "freq_success [A2, external]",
        "bit_success": "bit_success [A3, external]",
        "bit_baseline": "bit_baseline [A3, external]",
    })
    if "freq_success@noise0" in table_md.columns:
        table_md = table_md.rename(columns={"freq_success@noise0": "freq_success@noise0 [A2, external]"})
    write_markdown(table_md, out / "table_baselines.md")
    print("\nBaseline comparison (mean ± 95% CI, evaluation seeds)\n", table.to_string(index=False))

    # ---------- hypothesis tests ----------
    res = {"noise": a.noise, "standard": [sl, sk], "tuned": selected_config,
           "selected_config": selected_config,
           "selection_seeds": [int(s) for s in sel_seeds],
           "evaluation_seeds": [int(s) for s in eval_seeds],
           "eval_seeds": [int(s) for s in eval_seeds],
           "n_selection": len(sel_seeds), "n_evaluation": len(eval_seeds),
           "minimum_attainable_p": float(2.0 / (2.0 ** len(eval_seeds))),
           "holm_family": ["f1", "reid_top1", "freq_success", "bit_success"],
           "underpowered": len(eval_seeds) < 12,
           "selection_note": note,
           "limitations": {
               "entities": "Seeds share the same prepared population and vary the noise realization, split and victim sample.",
               "generalizability": "P-values describe replicate variability on the current dataset and do not establish generalizability to other datasets.",
               "selection_leakage": "The tuned configuration is selected using the same entity set, with entity-level tuning/evaluation leakage caveat.",
           }}
    if res["underpowered"]:
        print("WARNING: fewer than 12 evaluation seeds; results are underpowered.", file=sys.stderr)
    std_e = parts[f"standard_bf_l{sl}_k{sk}"].sort_values("seed")
    tun_e = parts[f"tuned_bf_l{tl}_k{tk}"].sort_values("seed")
    paired = {}
    paired_raw_p = []
    for m in ["f1", "reid_top1", "freq_success", "bit_success"]:
        differences, total_n = merge_paired(std_e, tun_e, m)
        x = std_e.merge(tun_e, on="seed", validate="one_to_one", suffixes=("_standard", "_tuned"))
        standard_values = x[f"{m}_standard"].to_numpy(dtype=float)
        tuned_values = x[f"{m}_tuned"].to_numpy(dtype=float)
        effective_n = len(differences)
        if effective_n >= 1:
            w = stats.wilcoxon(differences, alternative="two-sided")
            p = float(w.pvalue)
        else:
            p = None
        # The exact minimum achievable two-sided p cannot be less than 1 / 2^n.
        minimum_p = float(2.0 / (2.0 ** effective_n)) if effective_n > 0 else None
        effect = paired_effect(differences, rng_seed=sweep.effect_seed, bootstrap_draws=sweep.bootstrap_draws)
        std_mean = float(standard_values.mean())
        tun_mean = float(tuned_values.mean())
        abs_diff_pp = (tun_mean - std_mean) * 100.0  # percentage points, positive = tuned better
        rel_diff_pct = (abs_diff_pp / (abs(std_mean) * 100.0 + 1e-12)) * 100.0  # % relative
        # Rename HL key to clarify sign convention: positive = tuned better
        hl_val = effect.pop("hodges_lehmann", None)
        hl_ci = effect.pop("hl_ci95", None)
        effect["hodges_lehmann_tuned_minus_standard"] = hl_val
        effect["hl_ci95_tuned_minus_standard"] = hl_ci
        paired[m] = {
            "standard_mean": std_mean,
            "tuned_mean": tun_mean,
            "abs_diff_pp": round(abs_diff_pp, 2),
            "abs_diff_pp_str": f"{abs_diff_pp:+.1f} pp",
            "rel_diff_pct": round(rel_diff_pct, 2),
            "rel_diff_pct_str": f"{rel_diff_pct:+.1f}% relative",
            "sign_convention": "tuned - standard (positive = tuned is better)",
            "n_total": int(total_n),
            "n_effective_after_zero_removal": int(effective_n),
            "minimum_achievable_p": minimum_p,
            "p": p,
            "effect": effect,
        }
        paired_raw_p.append(p)
    paired_adjusted = holm_bonferroni(
        np.array([1.0 if p is None else p for p in paired_raw_p], dtype=float)
    )
    for m, adjusted in zip(["f1", "reid_top1", "freq_success", "bit_success"], paired_adjusted):
        paired[m]["p_holm"] = None if paired[m]["p"] is None else float(adjusted)
    res["wilcoxon_standard_vs_tuned"] = paired

    per_seed = {"H1_rho_l_vs_top1": [], "H2_rho_k_vs_top1": [], "H3_rho_load_vs_f1": [], "H3_rho_load_vs_top1": []}
    for s, g in ev[ev.method == "bloom"].groupby("seed"):
        r1 = [stats.spearmanr(x.l, x.reid_top1)[0] for _, x in g.groupby("k") if x.l.nunique() > 2]
        r2 = [stats.spearmanr(x.k, x.reid_top1)[0] for _, x in g.groupby("l") if x.k.nunique() > 2]
        per_seed["H1_rho_l_vs_top1"].append(np.nanmean(r1) if r1 else np.nan)
        per_seed["H2_rho_k_vs_top1"].append(np.nanmean(r2) if r2 else np.nan)
        per_seed["H3_rho_load_vs_f1"].append(stats.spearmanr(g.load, g.f1)[0])
        per_seed["H3_rho_load_vs_top1"].append(stats.spearmanr(g.load, g.reid_top1)[0])
    expect = {"H1_rho_l_vs_top1": "expect > 0 (smaller l -> lower attack success)",
              "H2_rho_k_vs_top1": "expect < 0 (larger k -> lower attack success)",
              "H3_rho_load_vs_f1": "expect < 0 (more collisions -> lower F1)",
              "H3_rho_load_vs_top1": "expect < 0 (more collisions -> lower attack success)"}
    res["spearman_per_seed"] = {}
    trend_alternatives = {
        "H1_rho_l_vs_top1": "greater",
        "H2_rho_k_vs_top1": "less",
        "H3_rho_load_vs_f1": "less",
        "H3_rho_load_vs_top1": "less",
    }
    trend_names = list(per_seed)
    trend_raw = []
    for name in trend_names:
        vals = per_seed[name]
        v = np.array(vals, float); v = v[~np.isnan(v)]
        alternative = trend_alternatives[name]
        p = float(stats.wilcoxon(v, alternative=alternative).pvalue) if len(v) >= 5 and np.any(v != 0) else None
        rng = np.random.default_rng(2026)
        boot = [float(np.mean(rng.choice(v, size=len(v), replace=True))) for _ in range(2000)] if len(v) else []
        ci = np.quantile(boot, [0.025, 0.975]).tolist() if boot else [None, None]
        res["spearman_per_seed"][name] = {
            "mean_rho": float(v.mean()) if len(v) else None,
            "ci95_mean_rho": ci,
            "p_raw": p,
            "alternative": alternative,
            "expectation": expect[name],
        }
        trend_raw.append(p)
    trend_adjusted = holm_bonferroni(
        np.array([1.0 if p is None else p for p in trend_raw], dtype=float)
    )
    for name, adjusted in zip(trend_names, trend_adjusted):
        res["spearman_per_seed"][name]["p_holm"] = (
            None if res["spearman_per_seed"][name]["p_raw"] is None else float(adjusted)
        )
    if selected_config is None:
        res["gate_result"] = {
            "passed": False,
            "reason": f"F1_MIN={a.f1_min} was unreachable on selection seeds",
        }
    elif "anonymity_set" in std_e and "anonymity_set" in tun_e:
        standard_privacy = float(std_e["anonymity_set"].median())
        tuned_privacy = float(tun_e["anonymity_set"].median())
        gain = tuned_privacy / standard_privacy if standard_privacy > 0 else float("inf")
        res["gate_result"] = {
            "passed": bool(gain >= a.min_privacy_gain),
            "privacy_gain_ratio": gain,
            "minimum_ratio": a.min_privacy_gain,
            "reason": "meaningful privacy gain" if gain >= a.min_privacy_gain
                      else "NO OPERATING POINT with meaningful privacy gain",
        }
    else:
        res["gate_result"] = {
            "passed": False,
            "reason": "anonymity_set metrics are unavailable",
        }
    (out / "stats.json").write_text(json.dumps(res, indent=2))
    print("\nHypothesis tests:\n", json.dumps(res["spearman_per_seed"], indent=2))
    print("Standard vs tuned:\n", json.dumps(paired, indent=2))

    # ---------- sensitivity and feasibility tables (T1) ----------
    bloom_all = main_df[main_df.method == "bloom"]
    if "f1_unc" in bloom_all.columns and "feasible_01" in bloom_all.columns:
        # Sensitivity table: per (l, k, noise), mean of f1_unc / f1_05 / f1_01 / feasibility
        sens_rows = []
        for (lv, kv, nv), grp in bloom_all.groupby(["l", "k", "noise"]):
            sens_rows.append({
                "l": lv, "k": kv, "noise": nv,
                "f1_unc": grp["f1_unc"].mean() if "f1_unc" in grp else float("nan"),
                "f1_05": grp["f1_05"].mean() if "f1_05" in grp else float("nan"),
                "f1_01": grp["f1_01"].mean() if "f1_01" in grp else float("nan"),
                "feasible_05": bool(grp["feasible_05"].all()) if "feasible_05" in grp else False,
                "feasible_01": bool(grp["feasible_01"].all()) if "feasible_01" in grp else False,
                "n_seeds": grp["seed"].nunique(),
            })
        sens_df = pd.DataFrame(sens_rows)
        write_run_csv(sens_df, out / "table_sensitivity_fpr.csv",
                      q=metas[0][1]["experiment_config"]["q"],
                      pad=metas[0][1]["experiment_config"]["pad"],
                      data_mode=metas[0][1]["experiment_config"]["data_mode"],
                      source_runs=source_runs, analysis_scope=analysis_scope)
        print(f"\nSensitivity table -> {out / 'table_sensitivity_fpr.csv'}")

        # Feasibility table: per (l, k, noise), fraction of seeds feasible_01
        feas_rows = []
        for (lv, kv, nv), grp in bloom_all.groupby(["l", "k", "noise"]):
            n_total = len(grp)
            n_feasible = int(grp["feasible_01"].sum()) if "feasible_01" in grp else 0
            feas_rows.append({
                "l": lv, "k": kv, "noise": nv,
                "n_feasible_01": n_feasible,
                "n_total": n_total,
                "frac_feasible_01": n_feasible / n_total if n_total > 0 else float("nan"),
            })
        feas_df = pd.DataFrame(feas_rows)
        write_run_csv(feas_df, out / "table_feasibility.csv",
                      q=metas[0][1]["experiment_config"]["q"],
                      pad=metas[0][1]["experiment_config"]["pad"],
                      data_mode=metas[0][1]["experiment_config"]["data_mode"],
                      source_runs=source_runs, analysis_scope=analysis_scope)
        print(f"Feasibility table -> {out / 'table_feasibility.csv'}")

    # ---------- figures ----------
    am = aggregate(bf, ["l", "k"])
    ls, ks = sorted(am.l.unique(), reverse=True), sorted(am.k.unique())

    # Build infeasible mask for heatmap hatching
    infeasible_mask = None
    if "feasible_01" in bf.columns:
        feas_grp = bf.groupby(["l", "k"])["feasible_01"].all().reset_index()
        feas_grp["infeasible_all"] = ~feas_grp["feasible_01"]
        infeasible_piv = feas_grp.pivot(index="l", columns="k", values="infeasible_all").reindex(index=ls, columns=ks)
        infeasible_mask = infeasible_piv

    f1_col_mean = "f1_mean"
    fig, axs = plt.subplots(1, 4, figsize=(17, 3.8))
    for ax, (col, title, kw) in zip(axs, [(f1_col_mean, "Test F1 (primary utility)", {}),
                                          ("reid_top1_mean", "Re-identification top-1 (A1 attack)", {"cmap": "Oranges"}),
                                          ("freq_success_mean", "Frequency-attack success (A2)", {"cmap": "Oranges"}),
                                          ("fill_mean", "Fill ratio", {"cmap": "Greens"})]):
        piv = am.pivot(index="l", columns="k", values=col).reindex(index=ls, columns=ks)
        heatmap(ax, piv, title, infeasible_mask=infeasible_mask if col == f1_col_mean else None, **kw)
    fig.suptitle(f"(l, k) grid at noise={a.noise}", y=1.02); fig.tight_layout()
    fig.savefig(figs / "heatmaps.png", bbox_inches="tight"); plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(11, 3.8))
    for ax, (xvar, grp) in zip(axs, [("l", "k"), ("k", "l")]):
        for c, gv in zip([BLUE, ORANGE, AQUA, MUTED], sorted(am[grp].unique())[::max(1, len(am[grp].unique()) // 4)]):
            s = am[am[grp] == gv].sort_values(xvar)
            ax.plot(s[xvar], s["reid_top1_mean"], "-o", color=c, label=f"{grp}={gv}  attack top-1", lw=2, ms=6)
            ax.plot(s[xvar], s[f1_col_mean], "--s", color=c, label=f"{grp}={gv}  F1", lw=1.2, ms=5, alpha=0.7)
        ax.set_xscale("log", base=2); ax.set_xlabel(xvar); ax.set_ylabel("rate"); ax.set_ylim(-0.02, 1.02)
        ax.legend(fontsize=7, ncol=2, frameon=False)
    fig.tight_layout(); fig.savefig(figs / "sweeps_l_k.png", bbox_inches="tight"); plt.close(fig)

    pts = [(getattr(r, f1_col_mean), r.reid_top1_mean, f"{int(r.l)}/{int(r.k)}") for r in am.itertuples() if r.fill_mean <= degenerate_fill]
    front = pareto_front(pts)
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=34, color=BLUE, label="non-degenerate (l/k)", zorder=3)
    dg = am[am.fill_mean > degenerate_fill]
    ax.scatter(dg[f1_col_mean], dg.reid_top1_mean, s=34, color=MUTED, marker="x",
               label=f"degenerate (fill>{degenerate_fill:.2f})")
    ax.plot([p[0] for p in front], [p[1] for p in front], color=ORANGE, lw=2, label="Pareto front", zorder=2)
    for f, t, lab in front:
        ax.annotate(lab, (f, t), fontsize=6.5, xytext=(3, 3), textcoords="offset points", color=MUTED)
    e = ex[ex.seed.isin(seeds)]
    ax.scatter(e.f1.mean(), e.reid_top1.mean(), s=70, color=AQUA, marker="D", label="exact hash (A1: key leaked)", zorder=4)
    ax.set_xlabel("utility: test F1 (higher is better)"); ax.set_ylabel("privacy loss: re-id top-1 (lower is better)")
    ax.set_title(f"Privacy-utility trade-off (noise={a.noise})"); ax.legend(fontsize=7, frameon=False)
    fig.tight_layout(); fig.savefig(figs / "pareto.png", bbox_inches="tight"); plt.close(fig)
    write_run_csv(pd.DataFrame(front, columns=["f1", "reid_top1", "config"]),
                  out / "pareto_front.csv",
                  q=metas[0][1]["experiment_config"]["q"],
                  pad=metas[0][1]["experiment_config"]["pad"],
                  data_mode=metas[0][1]["experiment_config"]["data_mode"],
                  source_runs=source_runs,
                  analysis_scope=analysis_scope)

    # noise robustness
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.6))
    noise_f1_col = "f1"
    series = [("exact hash", main_df[main_df.method == "exact_hash"], AQUA),
              (f"standard BF {sl}/{sk}", main_df[(main_df.method == "bloom") & (main_df.l == sl) & (main_df.k == sk)], BLUE),
              (f"tuned BF {tl}/{tk}", main_df[(main_df.method == "bloom") & (main_df.l == tl) & (main_df.k == tk)], ORANGE)]
    for ax, (m, ttl) in zip(axs, [(noise_f1_col, "Test F1 (primary utility)"), ("reid_top1", "Re-identification top-1")]):
        for name, part, c in series:
            if m in part.columns:
                g = part.groupby("noise")[m].mean()
                ax.plot(g.index, g.values, "-o", color=c, label=name, lw=2)
        ax.set_xlabel("typo noise rate"); ax.set_title(ttl); ax.set_ylim(-0.02, 1.02)
    axs[0].legend(fontsize=7, frameon=False); fig.tight_layout()
    fig.savefig(figs / "noise_robustness.png", bbox_inches="tight"); plt.close(fig)

    # optional: overlap + DP
    if a.overlap_csv:
        ov = read_csv(a.overlap_csv)
        ov = ov[(ov.noise == a.noise) & (ov.method == "bloom")]
        ovs = ov.groupby(["l", "k", "overlap"])[["f1", "reid_top1", "freq_success"]].mean().reset_index()
        write_run_csv(ovs, out / "table_overlap.csv",
                      q=metas[0][1]["experiment_config"]["q"],
                      pad=metas[0][1]["experiment_config"]["pad"],
                      data_mode=metas[0][1]["experiment_config"]["data_mode"],
                      source_runs=source_runs,
                      analysis_scope=analysis_scope)
        print("\nDictionary-overlap sensitivity (E2.7)\n", ovs.to_string(index=False))
    if a.dp:
        dp = read_csv(a.dp)
        dp["eps"] = dp["eps"].astype(float)
        available = [metric for metric in ("f1", "reid_top1", "freq_success", "bit_success", "flip_p") if metric in dp]
        agg = dp.groupby(["l", "k", "eps"])[available].mean().reset_index()
        write_run_csv(agg, out / "table_dp.csv",
                      q=metas[0][1]["experiment_config"]["q"],
                      pad=metas[0][1]["experiment_config"]["pad"],
                      data_mode=metas[0][1]["experiment_config"]["data_mode"])
        print("\nDP ablation (E2.8)\n", agg.to_string(index=False))
        panels = [("f1", "Test F1")]
        if "reid_top1" in agg:
            panels.append(("reid_top1", "Re-identification top-1"))
        fig, axs = plt.subplots(1, len(panels), figsize=(5 * len(panels), 3.6), squeeze=False)
        for c, ((l, k), g) in zip([BLUE, ORANGE, AQUA, MUTED], agg.groupby(["l", "k"])):
            g = g[np.isfinite(g.eps)].sort_values("eps")
            for ax, (metric, _) in zip(axs[0], panels, strict=True):
                ax.plot(g.eps, g[metric], "-o", color=c, label=f"l={int(l)}, k={int(k)}", lw=2)
        for ax, (_, t) in zip(axs[0], panels, strict=True):
            ax.set_xscale("log", base=2); ax.set_xlabel("ε (smaller = more noise)"); ax.set_title(t); ax.set_ylim(-0.02, 1.02)
        axs[0, 0].legend(fontsize=7, frameon=False); fig.tight_layout()
        fig.savefig(figs / "dp_ablation.png", bbox_inches="tight"); plt.close(fig)
    manifest = {
        "source_runs": source_runs,
        "analysis_scope": analysis_scope,
        "tables": {
            name: str((out / name).resolve())
            for name in (
                "summary.csv",
                "table_baselines.csv",
                "table_baselines.md",
                "pareto_front.csv",
                "table_overlap.csv",
            )
            if (out / name).exists()
        },
        "figures": {
            name: str((figs / name).resolve())
            for name in (
                "heatmaps.png",
                "sweeps_l_k.png",
                "pareto.png",
                "noise_robustness.png",
            )
            if (figs / name).exists()
        },
    }
    (out / "consistency_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    print(f"\nfigures -> {figs}")


if __name__ == "__main__":
    main()
