from dataclasses import FrozenInstanceError
from pathlib import Path
from shutil import copyfile

import pytest
import yaml

from src.common.config import load_config
from src.common.paths import app_dir


def _write_override(directory: Path, override: str) -> None:
    copyfile(app_dir() / "configs" / "base.yaml", directory / "base.yaml")
    rq_defaults = yaml.safe_load((app_dir() / "configs" / "rq1.yaml").read_text(encoding="utf-8"))
    rq_defaults.update(yaml.safe_load(override))
    (directory / "rq1.yaml").write_text(yaml.safe_dump(rq_defaults), encoding="utf-8")


def test_loads_immutable_rq1_configuration():
    cfg = load_config("rq1")
    assert (cfg.bloom.l, cfg.bloom.k, cfg.bloom.q) == (1024, 4, 2)
    assert cfg.seeds == tuple(range(10))
    assert cfg.max_records_per_entity == 20
    assert cfg.sample_entities is None
    assert cfg.columns.text == ("raw_item_description", "dosage", "dosage_form", "pack_size")
    with pytest.raises(FrozenInstanceError):
        cfg.bloom.l = 512


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ("bloom: {l: 1000}", r"bloom\.l"),
        ("bloom: {k: 0}", r"bloom\.k"),
        ("bloom: {q: 0}", r"bloom\.q"),
        ("val_fraction: 1.2", "val_fraction"),
        ("seeds: [0, 0]", "seeds"),
        ("seeds: []", "seeds"),
        ("noise_levels: [1.1]", "noise_levels"),
        ("columns: {description: null}", "column names"),
    ],
)
def test_rejects_invalid_config(tmp_path, override, message):
    _write_override(tmp_path, override)
    with pytest.raises(ValueError, match=message):
        load_config("rq1", config_dir=tmp_path)


def test_rq_override_merges_nested_base_fields(tmp_path):
    _write_override(tmp_path, "bloom: {l: 512}\nseeds: [3, 4]\n")
    cfg = load_config("rq1", config_dir=tmp_path)
    assert cfg.seeds == (3, 4)
    assert (cfg.bloom.l, cfg.bloom.k, cfg.bloom.q) == (512, 4, 2)
