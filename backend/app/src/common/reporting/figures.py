"""Generate headless line charts and grouped bars for experiment summaries."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes

_PALETTE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7")
_MARKERS = ("o", "s", "^", "D")
_LINESTYLES = ("--", "-.", "-", ":")


def _series(df: pd.DataFrame, group: str) -> list[tuple[object, pd.DataFrame]]:
    series = list(df.groupby(group, sort=False, observed=True))
    if not 1 <= len(series) <= len(_PALETTE):
        raise ValueError("Charts require one to four series")
    return series


def _error_bars(
    ax: Axes, x: np.ndarray, points: pd.DataFrame, y: str, yerr: str | None, color: str
) -> None:
    if yerr is not None:
        values, errors = points[y].to_numpy(dtype=float), points[yerr].to_numpy(dtype=float)
        valid = np.isfinite(values) & np.isfinite(errors)
        if valid.any():
            ax.errorbar(x[valid], values[valid], yerr=errors[valid], fmt="none", ecolor=color, capsize=4)


def _finish(ax: Axes, title: str, xlabel: str, ylabel: str, path: str | Path, score_axis: bool) -> None:
    ax.set(title=title, xlabel=xlabel, ylabel=ylabel)
    if score_axis:
        ax.set_ylim(0, 1)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#dddddd", linewidth=0.7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    ax.figure.savefig(destination, dpi=200, format="png")


def line_chart(
    df: pd.DataFrame, x: str, y: str, yerr: str | None, group: str, title: str,
    xlabel: str, ylabel: str, path: str | Path, *, score_axis: bool = True,
) -> None:
    """Draw grouped lines and show error bars only where uncertainty is available."""
    series = _series(df, group)
    with plt.rc_context({"font.size": 11}):
        fig, ax = plt.subplots(figsize=(8, 4.8), layout="constrained")
        try:
            for i, (label, points) in enumerate(series):
                points = points.sort_values(x)
                coordinates = points[x].to_numpy()
                ax.plot(
                    coordinates, points[y], label=str(label), color=_PALETTE[i],
                    linestyle=_LINESTYLES[i], marker=_MARKERS[i], linewidth=1.8,
                )
                _error_bars(ax, coordinates, points, y, yerr, _PALETTE[i])
            if pd.api.types.is_numeric_dtype(df[x]):
                ax.set_xticks(sorted(df[x].unique()))
            _finish(ax, title, xlabel, ylabel, path, score_axis)
        finally:
            plt.close(fig)


def grouped_bar_chart(
    df: pd.DataFrame, x: str, y: str, yerr: str | None, group: str, title: str,
    xlabel: str, ylabel: str, path: str | Path, *, score_axis: bool = True,
) -> None:
    """Draw grouped bars with one category tick and optional error bars."""
    series = _series(df, group)
    categories = df[x].drop_duplicates().tolist()
    centers = np.arange(len(categories), dtype=float)
    width = 0.8 / len(series)
    with plt.rc_context({"font.size": 11}):
        fig, ax = plt.subplots(figsize=(8, 4.8), layout="constrained")
        try:
            for i, (label, points) in enumerate(series):
                points = points.set_index(x).reindex(categories)
                positions = centers + width * (i - (len(series) - 1) / 2)
                ax.bar(positions, points[y], width, label=str(label), color=_PALETTE[i])
                _error_bars(ax, positions, points, y, yerr, "#333333")
            ax.set_xticks(centers, [str(value) for value in categories])
            _finish(ax, title, xlabel, ylabel, path, score_axis)
        finally:
            plt.close(fig)
