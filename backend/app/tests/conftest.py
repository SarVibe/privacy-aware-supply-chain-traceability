from dataclasses import replace
from pathlib import Path

import pytest

from src.common.config import load_config
from src.common.paths import app_dir


@pytest.fixture
def golden_config():
    cfg = load_config("rq1")
    data = (Path(__file__).parent / "golden" / "rq1").resolve().relative_to(app_dir())
    return replace(
        cfg,
        paths=replace(cfg.paths, prepared=str(data / "prepared"), splits=str(data / "splits"),
                      noisy=str(data / "noisy")),
    )
