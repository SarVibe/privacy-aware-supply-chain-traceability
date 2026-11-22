import pandas as pd

from src.common.reporting.tables import format_mean_std, save_table


def test_mean_std_rounding_and_missing_values():
    assert format_mean_std(0.9118, 0.0142) == "0.912 +- 0.014"
    assert format_mean_std(0.9118, 0.0142, digits=2) == "0.91 +- 0.01"
    assert format_mean_std(0.9, float("nan")) == "0.900 +- –"
    assert format_mean_std(float("nan"), 0.0) == "–"


def test_export_all_formats_without_literal_nan(tmp_path):
    base = tmp_path / "subdir" / "scores"
    save_table(pd.DataFrame({"method": ["raw_exact"], "score": [float("nan")]}), base)
    for extension in ("csv", "md", "tex"):
        contents = base.with_suffix(f".{extension}").read_text(encoding="utf-8")
        assert "method" in contents and "–" in contents
        assert "nan" not in contents.casefold()
