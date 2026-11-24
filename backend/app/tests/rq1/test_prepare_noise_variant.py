from dataclasses import replace

import pandas as pd

from experiments.rq1 import prepare_rq1_data
from src.common.config import load_config
from src.common.data.loader import load_noisy


def test_preparation_replays_all_fields_without_changing_default_artifacts(tmp_path, monkeypatch, golden_config):
    cfg = golden_config
    seed = cfg.seeds[0]
    control = load_noisy(seed, 0, cfg)
    variant = load_config("rq1_all_fields")
    monkeypatch.setattr(
        prepare_rq1_data, "load_config",
        lambda name: replace(cfg, noise_fields=variant.noise_fields) if name == "rq1_all_fields" else cfg,
    )
    monkeypatch.setattr(prepare_rq1_data, "noisy_csv_path", lambda *_: tmp_path / "noise.csv")
    args = ["--stage", "noise", "--all-fields", "--seeds", str(seed), "--noise-levels", "15"]
    original_default = load_noisy(seed, 0.15, cfg)
    prepare_rq1_data.main(args)
    emitted = (tmp_path / "noise.csv").read_bytes()
    logged = (tmp_path / "noise_log.csv").read_bytes()
    prepare_rq1_data.main(args)
    assert (tmp_path / "noise.csv").read_bytes() == emitted
    assert (tmp_path / "noise_log.csv").read_bytes() == logged
    prepared = pd.read_csv(tmp_path / "noise.csv", dtype=str, keep_default_na=False)
    assert prepared.record_id.tolist() == control.record_id.tolist()
    assert prepared.entity_id.tolist() == control.entity_id.tolist()
    assert set(pd.read_csv(tmp_path / "noise_log.csv")["field"]) == set(cfg.columns.text)
    pd.testing.assert_frame_equal(load_noisy(seed, 0.15, cfg), original_default)
