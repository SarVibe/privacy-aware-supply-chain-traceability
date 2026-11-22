import pandas as pd

from src.common.config import load_config
from src.common.data.splitting import apply_split
from src.common.linking.bloom import BloomLinker
from src.common.linking.threshold import select_per_noise_tau, select_single_tau, tune_tau


def test_single_and_per_noise_choose_different_thresholds():
    table = pd.DataFrame(
        [(0.0, 0.7, 0.9), (0.0, 0.8, 0.8), (0.0, 0.9, 0.7),
         (0.15, 0.7, 0.1), (0.15, 0.8, 0.7), (0.15, 0.9, 0.7)],
        columns=["noise_level", "tau", "f1"],
    )
    assert select_single_tau(table) == 0.8
    assert select_per_noise_tau(table) == {0.0: 0.7, 0.15: 0.9}


def test_higher_tau_wins_single_and_per_noise_ties():
    table = pd.DataFrame(
        [(0.0, 0.9, 0.75), (0.0, 0.8, 0.75), (0.15, 0.8, 0.5), (0.15, 0.9, 0.5)],
        columns=["noise_level", "tau", "f1"],
    )
    assert select_single_tau(table) == 0.9
    assert select_per_noise_tau(table) == {0.0: 0.9, 0.15: 0.9}


def test_tuning_prepares_validation_once_per_level_and_is_invariant_to_test_changes(monkeypatch):
    cfg = load_config("rq1")
    base = pd.DataFrame({
        "record_id": ["r1", "r2", "r3", "r4", "r5", "r6"],
        "entity_id": ["v1", "v1", "v2", "t1", "t1", "t2"],
        "raw_item_description": ["Alpha 10mg", "Alpha 10mg", "Beta 10mg", "X", "X", "Y"],
    })
    noisy = base.copy()
    noisy.loc[1, "raw_item_description"] = "Alpa 10mg"
    full_by_level = {0.0: base, 0.15: noisy}
    split = {"validation": ["v1", "v2"], "test": ["t1", "t2"]}
    grid = [0.7, 0.8, 0.9]
    args = {"cfg": cfg, "field_set": "description"}

    prepare = BloomLinker.prepare
    calls = []

    def observe(linker, frame, tau_min):
        assert cfg.columns.entity_id not in frame
        assert set(frame.record_id) == {"r1", "r2", "r3"}
        calls.append(tau_min)
        return prepare(linker, frame, tau_min)

    monkeypatch.setattr(BloomLinker, "prepare", observe)
    validation = {level: apply_split(frame, split, cfg)[0] for level, frame in full_by_level.items()}
    first = tune_tau(validation, grid, args)
    modified = {}
    for level, frame in full_by_level.items():
        val, test = apply_split(frame, split, cfg)
        changed_test = test.iloc[::-1].assign(raw_item_description=["Alpha", "Yankee", "Z"])
        modified[level] = apply_split(pd.concat([changed_test, val]), split, cfg)[0]
    replay = tune_tau(modified, grid, args)
    assert calls == [0.7] * 4
    assert first.columns.tolist() == ["noise_level", "tau", "precision", "recall", "f1"]
    assert len(first) == 2 * len(grid)
    pd.testing.assert_frame_equal(first, replay)
    assert select_single_tau(first) == select_single_tau(replay)
    assert select_per_noise_tau(first) == select_per_noise_tau(replay)
