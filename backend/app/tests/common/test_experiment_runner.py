import pandas as pd
import pytest

from src.common.experiment.runner import RunRecorder, iter_grid, timed


def test_grid_preserves_axis_and_value_insertion_order():
    grid = list(iter_grid({"field": ["description", "composite"], "seed": [1, 0]}))
    assert grid == [
        {"field": "description", "seed": 1},
        {"field": "description", "seed": 0},
        {"field": "composite", "seed": 1},
        {"field": "composite", "seed": 0},
    ]
    assert list(iter_grid({"x": []})) == []
    assert list(iter_grid({})) == [{}]


def test_recorder_orders_columns_fills_missing_and_rejects_unknown_keys():
    recorder = RunRecorder(["seed", "tau", "method"])
    recorder.add({"method": "raw_exact", "seed": 0})
    with pytest.raises(ValueError, match="extra"):
        recorder.add({"extra": "unexpected"})
    frame = recorder.to_frame()
    assert frame.columns.tolist() == ["seed", "tau", "method"]
    assert len(frame) == 1 and pd.isna(frame.loc[0, "tau"])


def test_timed_returns_frozen_non_negative_seconds():
    with timed() as elapsed:
        inside = elapsed()
    value = elapsed()
    assert isinstance(value, float)
    assert value >= inside >= 0
    assert elapsed() == value
