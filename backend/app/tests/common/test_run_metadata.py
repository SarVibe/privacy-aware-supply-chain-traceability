import hashlib
import json
import subprocess
from datetime import datetime

from src.common.config import load_config
from src.common.experiment_metadata import write_metadata


def test_metadata_contains_provenance_without_the_hmac_key(tmp_path):
    cfg = load_config("rq1")
    destination = tmp_path / "nested" / "metadata.json"
    write_metadata(destination, cfg, (0, 1), extra={"smoke": False})
    text = destination.read_text(encoding="utf-8")
    metadata = json.loads(text)
    assert datetime.fromisoformat(metadata["timestamp"]).tzinfo is not None
    assert metadata["platform"] and metadata["seeds"] == [0, 1]
    assert metadata["extra"] == {"smoke": False}
    assert all(metadata["package_versions"][name] for name in ("python", "numpy", "pandas", "scipy"))
    assert "git_commit" in metadata
    bloom = metadata["config"]["bloom"]
    assert bloom["l"] == cfg.bloom.l
    assert "hmac_key" not in bloom and cfg.bloom.hmac_key not in text
    assert bloom["hmac_key_fingerprint"] == hashlib.sha256(bytes.fromhex(cfg.bloom.hmac_key)).hexdigest()[:12]


def test_metadata_uses_null_when_git_is_unavailable(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", unavailable)
    destination = tmp_path / "metadata.json"
    write_metadata(destination, load_config("rq1"), [0])
    assert json.loads(destination.read_text(encoding="utf-8"))["git_commit"] is None
