import matplotlib
import pandas as pd
import pytest

from src.common.reporting.figures import grouped_bar_chart, line_chart


@pytest.mark.parametrize("plot", [line_chart, grouped_bar_chart])
def test_headless_chart_writes_png_with_partial_uncertainty(tmp_path, plot):
    frame = pd.DataFrame({
        "noise": [0, 5, 0, 5], "mean": [0.95, 0.7, 0.94, 0.8],
        "std": [float("nan"), 0.1, 0.02, float("nan")],
        "method": ["Exact", "Exact", "Fuzzy", "Fuzzy"],
    })
    path = tmp_path / "figures" / "chart.png"
    plot(frame, "noise", "mean", "std", "method", "Test scores", "Noise", "F1", path)
    assert matplotlib.get_backend().lower() == "agg"
    assert path.stat().st_size > 1024
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
