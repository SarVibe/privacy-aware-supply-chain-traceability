"""Aggregate results -> tables, hypothesis tests (H1-H3), operating-point selection and figures.

  python -m experiments.rq2.results_analyzer --grid backend/app/results/rq2/raw/exp2_grid.csv [--dp backend/app/results/rq2/raw/exp2_dp.csv] [--noise 0.15]

Operating-point selection uses the first half of the seeds; the baseline comparison and the
Wilcoxon tests use the remaining seeds, so the 'tuned' configuration is not evaluated on the
data that selected it.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from src.application_config import Config
from src.common.experiment_metadata import write_markdown, write_run_csv, parse_standard
from src.rq2.results_schema import validate_results, SchemaError
from src.rq2.experiment_config import EXPERIMENT_CONFIG

BLUE, ORANGE, AQUA, INK, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e"
METRICS = ["precision", "recall", "f1", "fpr", "auc", "reid_top1", "reid_top5", "reid_ties", "reid_cands_delta",
           "freq_success", "bit_success", "bit_baseline", "fill", "entropy", "load", "tau"]
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": "#e6e5e1",
                     "grid.linewidth": 0.6, "figure.dpi": 130})


def ci95(x):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    return float(stats.t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / math.sqrt(len(x))) if len(x) > 1 else float("nan")


def aggregate(df, keys):
    g = df.groupby(keys, dropna=False)
    out = g[METRICS].mean().add_suffix("_mean")
    out = out.join(g[METRICS].std().add_suffix("_std")).join(g[METRICS].agg(ci95).add_suffix("_ci95"))
    out["n_seeds"] = g["seed"].nunique()
    return out.reset_index()


def heatmap(ax, piv, title, fmt="{:.2f}", cmap="Blues", vmin=0, vmax=1):
    im = ax.imshow(piv.values, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    ax.set_xticks(range(piv.shape[1])); ax.set_xticklabels(piv.columns)
    ax.set_yticks(range(piv.shape[0])); ax.set_yticklabels(piv.index)
    ax.set_xlabel("k (hash functions)"); ax.set_ylabel("l (filter length)"); ax.set_title(title, fontsize=10)
    ax.grid(False)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            if not np.isnan(v):
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


def holm_bonferroni(p_values):
    """Return adjusted p-values for a test family."""
    p_values = np.asarray(p_values, dtype=float)
    m = len(p_values)
    order = np.argsort(p_values)
    adjusted = np.empty(m, dtype=float)
    running = 0.0
    for rank, index in enumerate(order):
        adjusted[index] = min(1.0, max(running, (m - rank) * p_values[index]))
        running = adjusted[index]
    return adjusted


def paired_effect(differences, rng_seed=2026):
    differences = np.asarray(differences, dtype=float)
    differences = differences[~np.isnan(differences)]
    if len(differences) == 0:
        return {"n": 0, "hodges_lehmann": None, "hl_ci95": [None, None],
                "rank_biserial": None, "cohens_dz": None}
    pairwise = (differences[:, None] + differences[None, :]) / 2.0
    hl = float(np.median(pairwise.ravel()))
    rng = np.random.default_rng(rng_seed)
    boot = []
    for _ in range(2000):
        sample = rng.choice(differences, size=len(differences), replace=True)
        pairwise_boot = (sample[:, None] + sample[None, :]) / 2.0
        boot.append(float(np.median(pairwise_boot.ravel())))
    ci = np.quantile(boot, [0.025, 0.975]).tolist()
    positive = np.sum(differences > 0)
    negative = np.sum(differences < 0)
    r = (positive - negative) / (positive + negative) if positive + negative else 0.0
    dz = float(differences.mean() / differences.std(ddof=1)) if len(differences) > 1 and differences.std(ddof=1) > 0 else 0.0
    return {"n": int(len(differences)), "hodges_lehmann": hl,
            "hl_ci95": [float(ci[0]), float(ci[1])],
            "rank_biserial": float(r), "cohens_dz": dz}


def merge_paired(a: pd.DataFrame, b: pd.DataFrame, metric: str):
    if "seed" not in a or "seed" not in b:
        raise ValueError("paired comparison requires a seed column")
    a_seeds = set(a["seed"].tolist())
    b_seeds = set(b["seed"].tolist())
    if a_seeds != b_seeds:
        raise ValueError(f"paired seed sets do not match: {sorted(a_seeds)} != {sorted(b_seeds)}")
    merged = a.merge(b, on="seed", validate="one_to_one",
                     suffixes=("_standard", "_tuned"))
    x = merged[f"{metric}_standard"].to_numpy(dtype=float)
    y = merged[f"{metric}_tuned"].to_numpy(dtype=float)
    differences = x - y
    differences = differences[differences != 0]
    return differences, len(merged)


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
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default=str(Config.RQ2_RAW_DIR / "exp2_grid.csv"))
    ap.add_argument("--dp", default=None)
    ap.add_argument("--overlap-csv", default=None, help="optional CSV from the E2.7 overlap run")
    ap.add_argument("--noise", type=float, default=0.05, help="noise level used for the main analysis")
    ap.add_argument("--f1-min", type=float, default=0.85, help="utility constraint for the operating point")
    ap.add_argument("--outdir", default=str(Config.RQ2_TABLES_DIR))
    ap.add_argument("--standard", default="1024:4", help="standard Bloom configuration as l:k")
    a = ap.parse_args()
    try:
        sl, sk = parse_standard(a.standard)
    except ValueError as exc:
        ap.error(str(exc))
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    figs = Config.RQ2_FIGURES_DIR
    figs.mkdir(parents=True, exist_ok=True)
    metas = [("grid", load_run_meta(a.grid))]
    if a.dp:
        metas.append(("dp", load_run_meta(a.dp)))
    if a.overlap_csv:
        metas.append(("overlap", load_run_meta(a.overlap_csv)))
    degenerate_fill = float(metas[0][1]["experiment_config"]["degenerate_fill"])
    validate_run_metas(metas, degenerate_fill)

    df = pd.read_csv(a.grid)
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
    df["eps"] = df["eps"].replace([np.inf], np.inf)
    main_df = df[df.overlap == 1.0]

    # ---------- summary of everything ----------
    summary = aggregate(main_df, ["method", "l", "k", "noise", "eps"])
    write_run_csv(summary, out / "summary.csv",
                  q=metas[0][1]["experiment_config"]["q"],
                  pad=metas[0][1]["experiment_config"]["pad"],
                  data_mode=metas[0][1]["experiment_config"]["data_mode"])

    d = main_df[(main_df.noise == a.noise)]
    if d.empty:
        raise SystemExit(f"no rows with noise={a.noise}; available: {sorted(main_df.noise.unique())}")
    bf = d[d.method == "bloom"]
    ex = d[d.method == "exact_hash"]
    seeds = sorted(d.seed.unique())
    sel_seeds = seeds[: max(1, math.ceil(len(seeds) / 2))]
    eval_seeds = [s for s in seeds if s not in sel_seeds] or seeds
    if eval_seeds == seeds and len(seeds) > 1:
        print("WARNING: too few seeds to split selection/evaluation; using all seeds for both.")

    # ---------- operating-point selection (selection seeds only) ----------
    sel = bf[bf.seed.isin(sel_seeds)].groupby(["l", "k"])[["f1", "reid_top1", "fill"]].mean().reset_index()
    cand = sel[(sel.fill <= degenerate_fill)]
    ok = cand[cand.f1 >= a.f1_min]
    note = ""
    if ok.empty:
        thr = 0.9 * cand.f1.max()
        ok = cand[cand.f1 >= thr]
        note = f"no config reached F1>={a.f1_min}; relaxed to 0.9*best F1 = {thr:.3f}"
    tuned = ok.sort_values(["reid_top1", "f1"], ascending=[True, False]).iloc[0]
    tl, tk = int(tuned.l), int(tuned.k)
    sl, sk = sl, sk
    print(f"standard=({sl},{sk})  tuned=({tl},{tk})  {note}")

    # ---------- baseline comparison table (evaluation seeds) ----------
    ev = d[d.seed.isin(eval_seeds)]
    parts = {"exact_hash": ev[ev.method == "exact_hash"],
             f"standard_bf_l{sl}_k{sk}": ev[(ev.method == "bloom") & (ev.l == sl) & (ev.k == sk)],
             f"tuned_bf_l{tl}_k{tk}": ev[(ev.method == "bloom") & (ev.l == tl) & (ev.k == tk)]}
    cols = ["precision", "recall", "f1", "auc", "reid_top1", "reid_top5", "reid_cands_delta", "freq_success",
            "bit_success", "bit_baseline", "fill", "entropy"]
    rows = []
    for name, part in parts.items():
        r = {"setup": name, "n_seeds": part.seed.nunique()}
        for c in cols:
            r[c] = f"{part[c].mean():.3f} ± {ci95(part[c]):.3f}" if part[c].notna().any() else "n/a"
        rows.append(r)
    table = pd.DataFrame(rows)
    # The frequency attack (A2) is only informative when stored records of one entity coincide,
    # i.e. at noise = 0 (with typos every record is unique for *every* method). Report that case too.
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
                  data_mode=metas[0][1]["experiment_config"]["data_mode"])
    write_markdown(table, out / "table_baselines.md")
    print("\nBaseline comparison (mean ± 95% CI, evaluation seeds)\n", table.to_string(index=False))

    # ---------- hypothesis tests ----------
    res = {"noise": a.noise, "standard": [sl, sk], "tuned": [tl, tk],
           "selection_seeds": [int(s) for s in sel_seeds], "eval_seeds": [int(s) for s in eval_seeds],
           "selection_note": note,
           "limitations": {
               "entities": "All seeds use the same fixed entity set; the key, noise realization, split, and victim sample vary.",
               "generalizability": "P-values describe replicate variability on the current dataset and do not establish generalizability to other datasets.",
               "selection_leakage": "The tuned configuration is selected using the same entity set, with entity-level tuning/evaluation leakage caveat.",
           }}
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
        minimum_p = float(2.0 ** (-effective_n)) if effective_n > 0 else None
        effect = paired_effect(differences)
        paired[m] = {
            "standard_mean": float(standard_values.mean()),
            "tuned_mean": float(tuned_values.mean()),
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
    for s, g in bf.groupby("seed"):
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
    (out / "stats.json").write_text(json.dumps(res, indent=2))
    print("\nHypothesis tests:\n", json.dumps(res["spearman_per_seed"], indent=2))
    print("Standard vs tuned:\n", json.dumps(paired, indent=2))

    # ---------- figures ----------
    am = aggregate(bf, ["l", "k"])
    ls, ks = sorted(am.l.unique(), reverse=True), sorted(am.k.unique())
    fig, axs = plt.subplots(1, 4, figsize=(17, 3.8))
    for ax, (col, title, kw) in zip(axs, [("f1_mean", "Test F1 (utility)", {}),
                                          ("reid_top1_mean", "Re-identification top-1 (A1 attack)", {"cmap": "Oranges"}),
                                          ("freq_success_mean", "Frequency-attack success (A2)", {"cmap": "Oranges"}),
                                          ("fill_mean", "Fill ratio", {"cmap": "Greens"})]):
        heatmap(ax, am.pivot(index="l", columns="k", values=col).reindex(index=ls, columns=ks), title, **kw)
    fig.suptitle(f"(l, k) grid at noise={a.noise}", y=1.02); fig.tight_layout()
    fig.savefig(figs / "heatmaps.png", bbox_inches="tight"); plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(11, 3.8))
    for ax, (xvar, grp) in zip(axs, [("l", "k"), ("k", "l")]):
        for c, gv in zip([BLUE, ORANGE, AQUA, MUTED], sorted(am[grp].unique())[::max(1, len(am[grp].unique()) // 4)]):
            s = am[am[grp] == gv].sort_values(xvar)
            ax.plot(s[xvar], s["reid_top1_mean"], "-o", color=c, label=f"{grp}={gv}  attack top-1", lw=2, ms=6)
            ax.plot(s[xvar], s["f1_mean"], "--s", color=c, label=f"{grp}={gv}  F1", lw=1.2, ms=5, alpha=0.7)
        ax.set_xscale("log", base=2); ax.set_xlabel(xvar); ax.set_ylabel("rate"); ax.set_ylim(-0.02, 1.02)
        ax.legend(fontsize=7, ncol=2, frameon=False)
    fig.tight_layout(); fig.savefig(figs / "sweeps_l_k.png", bbox_inches="tight"); plt.close(fig)

    pts = [(r.f1_mean, r.reid_top1_mean, f"{int(r.l)}/{int(r.k)}") for r in am.itertuples() if r.fill_mean <= degenerate_fill]
    front = pareto_front(pts)
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=34, color=BLUE, label="non-degenerate (l/k)", zorder=3)
    dg = am[am.fill_mean > degenerate_fill]
    ax.scatter(dg.f1_mean, dg.reid_top1_mean, s=34, color=MUTED, marker="x",
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
                  data_mode=metas[0][1]["experiment_config"]["data_mode"])

    # noise robustness
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.6))
    series = [("exact hash", main_df[main_df.method == "exact_hash"], AQUA),
              (f"standard BF {sl}/{sk}", main_df[(main_df.method == "bloom") & (main_df.l == sl) & (main_df.k == sk)], BLUE),
              (f"tuned BF {tl}/{tk}", main_df[(main_df.method == "bloom") & (main_df.l == tl) & (main_df.k == tk)], ORANGE)]
    for ax, (m, ttl) in zip(axs, [("f1", "Test F1"), ("reid_top1", "Re-identification top-1")]):
        for name, part, c in series:
            g = part.groupby("noise")[m].mean()
            ax.plot(g.index, g.values, "-o", color=c, label=name, lw=2)
        ax.set_xlabel("typo noise rate"); ax.set_title(ttl); ax.set_ylim(-0.02, 1.02)
    axs[0].legend(fontsize=7, frameon=False); fig.tight_layout()
    fig.savefig(figs / "noise_robustness.png", bbox_inches="tight"); plt.close(fig)

    # optional: overlap + DP
    if a.overlap_csv:
        ov = pd.read_csv(a.overlap_csv)
        ov = ov[(ov.noise == a.noise) & (ov.method == "bloom")]
        ovs = ov.groupby(["l", "k", "overlap"])[["f1", "reid_top1", "freq_success"]].mean().reset_index()
        write_run_csv(ovs, out / "table_overlap.csv",
                      q=metas[0][1]["experiment_config"]["q"],
                      pad=metas[0][1]["experiment_config"]["pad"],
                      data_mode=metas[0][1]["experiment_config"]["data_mode"])
        print("\nDictionary-overlap sensitivity (E2.7)\n", ovs.to_string(index=False))
    if a.dp:
        dp = pd.read_csv(a.dp)
        dp["eps"] = dp["eps"].astype(float)
        agg = dp.groupby(["l", "k", "eps"])[["f1", "reid_top1", "freq_success", "bit_success", "flip_p"]].mean().reset_index()
        write_run_csv(agg, out / "table_dp.csv",
                      q=metas[0][1]["experiment_config"]["q"],
                      pad=metas[0][1]["experiment_config"]["pad"],
                      data_mode=metas[0][1]["experiment_config"]["data_mode"])
        print("\nDP ablation (E2.8)\n", agg.to_string(index=False))
        fig, axs = plt.subplots(1, 2, figsize=(10, 3.6))
        for c, ((l, k), g) in zip([BLUE, ORANGE, AQUA, MUTED], agg.groupby(["l", "k"])):
            g = g[np.isfinite(g.eps)].sort_values("eps")
            axs[0].plot(g.eps, g.f1, "-o", color=c, label=f"l={int(l)}, k={int(k)}", lw=2)
            axs[1].plot(g.eps, g.reid_top1, "-o", color=c, label=f"l={int(l)}, k={int(k)}", lw=2)
        for ax, t in zip(axs, ["Test F1", "Re-identification top-1"]):
            ax.set_xscale("log", base=2); ax.set_xlabel("ε (smaller = more noise)"); ax.set_title(t); ax.set_ylim(-0.02, 1.02)
        axs[0].legend(fontsize=7, frameon=False); fig.tight_layout()
        fig.savefig(figs / "dp_ablation.png", bbox_inches="tight"); plt.close(fig)
    print(f"\nfigures -> {figs}")


if __name__ == "__main__":
    main()
