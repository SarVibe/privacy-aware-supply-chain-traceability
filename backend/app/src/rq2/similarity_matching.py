"""Dice similarity, threshold tuning and linkage-quality metrics.

Convention: D[i, j] = Dice(A_i, B_j); entity i of party A truly matches entity i
of party B (the diagonal). Everything else is a true non-match.
"""
import numpy as np
from collections import Counter
from scipy.stats import rankdata

from .experiment_config import TAU_GRID


def dice_matrix(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Pairwise Dice between rows of x (n,l) and rows of y (m,l) -> float64 (n,m)."""
    xf, yf = x.astype(np.float32), y.astype(np.float32)
    inter = (xf @ yf.T).astype(np.float64)
    denom = xf.sum(1).astype(np.float64)[:, None] + yf.sum(1).astype(np.float64)[None, :]
    return np.divide(2.0 * inter, denom, out=np.zeros_like(inter), where=denom > 0)


def _prf(tp, pred, n):
    p = tp / pred if pred > 0 else 0.0
    r = tp / n if n > 0 else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    fpr = (pred - tp) / (n * n - n) if n > 1 else 0.0
    return p, r, f1, fpr


def sweep(D: np.ndarray, taus=TAU_GRID):
    """Precision/recall/F1/FPR of the rule 'match iff Dice >= tau' for every tau."""
    n = D.shape[0]
    flat = np.sort(D.ravel())
    diag = np.sort(np.diag(D))
    out = []
    for t in taus:
        pred = flat.size - np.searchsorted(flat, t - 1e-12, side="left")
        tp = diag.size - np.searchsorted(diag, t - 1e-12, side="left")
        out.append(_prf(int(tp), int(pred), n))
    return np.array(out)  # columns: P, R, F1, FPR


def tune_tau(D_val: np.ndarray, taus=TAU_GRID) -> float:
    """Best-F1 threshold on the validation split (ties -> the higher, more conservative tau)."""
    res = sweep(D_val, taus)
    best = res[:, 2].max()
    return float(taus[np.flatnonzero(res[:, 2] >= best - 1e-12)[-1]])


def metrics_at(D: np.ndarray, tau: float) -> dict:
    p, r, f1, fpr = sweep(D, [tau])[0]
    return {"precision": p, "recall": r, "f1": f1, "fpr": fpr}


def auc_and_separation(D: np.ndarray):
    """Threshold-free utility: ROC-AUC of Dice (match vs non-match) and mean gap."""
    n = D.shape[0]
    pos = np.diag(D)
    mask = ~np.eye(n, dtype=bool)
    neg = D[mask]
    if n < 2:
        return float("nan"), float("nan")
    ranks = rankdata(np.concatenate([pos, neg]))
    auc = (ranks[:n].sum() - n * (n + 1) / 2) / (n * neg.size)
    return float(auc), float(pos.mean() - neg.mean())


def exact_metrics(tok_a: list, tok_b: list) -> dict:
    """Exact-match linkage: pair (i, j) is predicted iff tokens are equal."""
    n = len(tok_a)
    ca, cb = Counter(tok_a), Counter(tok_b)
    pred = sum(c * cb.get(t, 0) for t, c in ca.items())
    tp = sum(1 for a, b in zip(tok_a, tok_b) if a == b)
    p, r, f1, fpr = _prf(tp, pred, n)
    return {"precision": p, "recall": r, "f1": f1, "fpr": fpr}
