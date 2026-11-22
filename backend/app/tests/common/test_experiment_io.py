import pandas as pd

from src.common.experiment.io import read_csv, write_csv


def test_csv_preserves_column_order_literal_none_and_missing_numeric_values(tmp_path):
    frame = pd.DataFrame({"tau_mode": ["none", "single"], "tau": [float("nan"), 0.94]})
    path = tmp_path / "nested" / "raw_runs.csv"
    write_csv(frame, path)
    assert path.read_bytes().splitlines()[0] == b"tau_mode,tau"
    pd.testing.assert_frame_equal(read_csv(path), frame)
