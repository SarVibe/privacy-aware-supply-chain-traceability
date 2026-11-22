"""Format and export report tables in common publication formats."""

from pathlib import Path

import pandas as pd
from tabulate import tabulate

MISSING = "–"


def format_mean_std(mean: float, std: float, digits: int = 3) -> str:
    """Format a mean and sample standard deviation, using a dash for missing values."""
    if pd.isna(mean):
        return MISSING
    deviation = MISSING if pd.isna(std) else f"{std:.{digits}f}"
    return f"{mean:.{digits}f} +- {deviation}"


def save_table(df: pd.DataFrame, path_without_ext: str | Path) -> None:
    """Write index-free CSV, Markdown, and LaTeX with consistent missing cells."""
    base = Path(path_without_ext)
    base.parent.mkdir(parents=True, exist_ok=True)
    clean = df.astype(object).where(df.notna(), MISSING)
    clean.to_csv(base.with_name(base.name + ".csv"), index=False, encoding="utf-8", lineterminator="\n")
    markdown = tabulate(clean, headers="keys", showindex=False, tablefmt="github", disable_numparse=True)
    base.with_name(base.name + ".md").write_text(markdown + "\n", encoding="utf-8")
    latex = clean.to_latex(index=False, escape=True)
    base.with_name(base.name + ".tex").write_text(latex, encoding="utf-8")
