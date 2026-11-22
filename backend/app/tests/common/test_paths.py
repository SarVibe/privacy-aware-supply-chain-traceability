from src.common import paths
from src.common.config import load_config


def test_paths_resolve_under_app_and_create_only_on_request(tmp_path, monkeypatch):
    cfg = load_config("rq1")
    monkeypatch.setattr(paths, "app_dir", lambda: tmp_path)
    assert paths.raw_csv_path(cfg) == tmp_path / cfg.paths.raw / cfg.paths.raw_filename
    assert paths.prepared_dir(cfg) == tmp_path / cfg.paths.prepared
    assert not paths.prepared_dir(cfg).exists()
    assert paths.prepared_dir(cfg, create=True).is_dir()
    assert paths.splits_dir(cfg, create=True).is_dir()
    assert paths.noisy_dir(cfg, create=True).is_dir()
    assert paths.results_dir(cfg, "rq1", create=True) == tmp_path / cfg.paths.results / "rq1"
