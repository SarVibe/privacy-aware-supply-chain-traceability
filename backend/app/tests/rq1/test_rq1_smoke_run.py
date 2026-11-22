import json
import sys
from dataclasses import replace

import pandas as pd
import pytest

from experiments.rq1 import prepare_rq1_data, run_rq1
from src.common import paths
from src.common.config import load_config
from src.common.experiment.io import read_csv
from src.common.linking.threshold import select_per_noise_tau, select_single_tau

_EXPECTED_COLUMNS = [
    "run_id", "seed", "noise_level", "method", "field_set", "tau", "tau_mode", "split",
    "precision", "recall", "f1", "fragmentation_rate", "n_records", "n_entities",
    "n_pred_clusters", "runtime_sec",
]
_EXPECTED_GRID = {i / 100 for i in range(60, 100)}


@pytest.fixture
def prepared_experiment(tmp_path, monkeypatch):
    cfg = replace(load_config("rq1"), seeds=(0, 1))
    monkeypatch.setattr(paths, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(prepare_rq1_data, "load_config", lambda _: cfg)
    monkeypatch.setattr(run_rq1, "load_config", lambda _: cfg)
    source = paths.raw_csv_path(cfg)
    source.parent.mkdir(parents=True)
    raw = cfg.raw_columns
    pd.DataFrame(
        [
            {
                raw.description: f"Product {entity} 10mg Tablet 30",
                raw.molecule: f"Molecule {entity}",
                raw.dosage: "10mg",
                raw.dosage_form: "Tablet",
                raw.pack_size: "30",
            }
            for entity in range(12)
            for _ in range(3)
        ]
    ).to_csv(source, index=False)
    for stage in ("base", "split", "noise"):
        monkeypatch.setattr(sys, "argv", ["prepare_rq1_data", "--stage", stage])
        prepare_rq1_data.main()
    return cfg


def test_end_to_end_two_seed_run_and_determinism(tmp_path, prepared_experiment):
    first_dir, repeat_dir = tmp_path / "first", tmp_path / "repeat"
    flags = ["--seeds", "0", "1", "--noise-levels", "0", "5", "15%", "0.30", "--out-dir"]
    run_rq1.main([*flags, str(first_dir)])
    run_rq1.main([*flags, str(repeat_dir)])
    results = read_csv(first_dir / "raw_runs.csv")
    assert results.columns.tolist() == _EXPECTED_COLUMNS and len(results) == 64
    assert set(results.seed) == {0, 1}
    assert set(results.noise_level) == {0.0, 0.05, 0.15, 0.30}
    assert results.run_id.is_unique and results.split.eq("test").all()
    assert results.groupby(["seed", "noise_level", "field_set"]).size().eq(4).all()
    assert set(results.method) == {"raw_exact", "normalized_exact", "bloom_fuzzy"}
    exact = results.method.ne("bloom_fuzzy")
    assert results.tau.isna().equals(exact)
    assert results.loc[exact, "tau_mode"].eq("none").all()
    assert set(results.loc[~exact, "tau_mode"]) == {"single", "per_noise"}
    assert set(results.tau.dropna()) <= _EXPECTED_GRID
    assert results[["precision", "recall", "f1"]].apply(lambda s: s.between(0, 1)).all().all()
    assert results.fragmentation_rate.ge(1).all() and results.runtime_sec.ge(0).all()

    tuning_file = first_dir / "tau_selection.csv"
    tuning = read_csv(tuning_file)
    assert len(tuning) == 2 * 4 * 2 * len(_EXPECTED_GRID)
    assert set(tuning.tau) == _EXPECTED_GRID
    for (seed, field_set), validation in tuning.groupby(["seed", "field_set"]):
        fuzzy = results.loc[~exact & results.seed.eq(seed) & results.field_set.eq(field_set)]
        assert fuzzy.loc[fuzzy.tau_mode.eq("single"), "tau"].eq(select_single_tau(validation)).all()
        by_noise = fuzzy.loc[fuzzy.tau_mode.eq("per_noise")].set_index("noise_level").tau.to_dict()
        assert by_noise == select_per_noise_tau(validation)

    replay = read_csv(repeat_dir / "raw_runs.csv")
    pd.testing.assert_frame_equal(results.drop(columns="runtime_sec"), replay.drop(columns="runtime_sec"))
    assert tuning_file.read_bytes() == (repeat_dir / "tau_selection.csv").read_bytes()
    original_metadata = json.loads((first_dir / "metadata.json").read_text(encoding="utf-8"))
    repeated_metadata = json.loads((repeat_dir / "metadata.json").read_text(encoding="utf-8"))
    assert original_metadata.pop("timestamp") and repeated_metadata.pop("timestamp")
    assert original_metadata == repeated_metadata
    assert original_metadata["seeds"] == [0, 1]


def test_smoke_writes_seed_zero_to_dedicated_directory(prepared_experiment, capsys):
    regular = paths.results_dir(prepared_experiment, "rq1", create=True)
    sentinel = regular / "raw_runs.csv"
    sentinel.write_text("regular results\n", encoding="utf-8")
    run_rq1.main(["--smoke"])
    smoke_results = read_csv(regular / "smoke" / "raw_runs.csv")
    assert len(smoke_results) == 32 and smoke_results.seed.eq(0).all()
    with pytest.raises(SystemExit):
        run_rq1.main(["--smoke", "--out-dir", str(regular)])
    assert "writes only to results/rq1/smoke" in capsys.readouterr().err
    assert sentinel.read_text(encoding="utf-8") == "regular results\n"


def test_smoke_sample_is_deterministic_and_limits_entities():
    cfg = load_config("rq1")
    base = pd.DataFrame({"entity_id": [f"E{i:04d}" for i in range(402) for _ in range(2)]})
    sample = run_rq1._sample_for_smoke(base, cfg)
    assert len(sample) == 300
    assert sample == run_rq1._sample_for_smoke(base.iloc[::-1], cfg)
    assert run_rq1._sample_for_smoke(base, replace(cfg, sample_entities=400)) is None
