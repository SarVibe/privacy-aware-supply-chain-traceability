from dataclasses import replace

import pandas as pd

from experiments.rq2 import dp_ablation_runner as privacy_runner
from experiments.rq3 import dp_ablation_runner as utility_runner
from src.common.config import load_config
from src.common.experiment import dp_sweep


def test_rq3_and_rq2_dp_have_matching_record_utility(tmp_path, monkeypatch, golden_config):
    rq3 = replace(load_config("rq3"), paths=golden_config.paths)
    monkeypatch.setattr(dp_sweep, "load_config", lambda name: rq3 if name == "rq3" else load_config(name))
    options = ["--quick", "--configs", "1024:4", "--eps", "2", "inf"]
    utility_path = utility_runner.main([*options, "--out", str(tmp_path / "utility.csv")])
    privacy_path = privacy_runner.main([*options, "--out", str(tmp_path / "privacy.csv")])
    utility, privacy = pd.read_csv(utility_path), pd.read_csv(privacy_path)
    columns = ["seed", "noise", "eps", "flip_p", "tau", "precision", "recall", "f1", "n_records"]
    pd.testing.assert_frame_equal(utility[columns], privacy[columns], rtol=0, atol=1e-9)
    assert 0 < utility.loc[0, "flip_p"] < 0.5
    assert utility.loc[1, "flip_p"] == 0
    assert privacy["cross_party_f1"].between(0, 1).all()
