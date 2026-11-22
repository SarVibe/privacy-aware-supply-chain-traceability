"""Resolve configured paths against the backend application directory."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.common.config import Config


def app_dir() -> Path:
    """Return the absolute backend application directory."""
    return Path(__file__).resolve().parents[2]


def _directory(relative: str, create: bool = False) -> Path:
    root = app_dir()
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or path == root or not path.is_relative_to(root):
        raise ValueError(f"Expected an application-relative subdirectory, got {relative!r}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def raw_dir(cfg: "Config") -> Path:
    """Return the existing raw data directory."""
    return _directory(cfg.paths.raw)


def raw_csv_path(cfg: "Config") -> Path:
    """Return the configured raw CSV path."""
    directory = raw_dir(cfg)
    path = (directory / cfg.paths.raw_filename).resolve()
    if path.parent != directory or Path(cfg.paths.raw_filename).name != cfg.paths.raw_filename:
        raise ValueError("paths.raw_filename must name a file directly inside paths.raw")
    return path


def prepared_dir(cfg: "Config", *, create: bool = False) -> Path:
    """Return the prepared data directory and optionally create it."""
    return _directory(cfg.paths.prepared, create)


def splits_dir(cfg: "Config", *, create: bool = False) -> Path:
    """Return the split directory and optionally create it."""
    return _directory(cfg.paths.splits, create)


def noisy_dir(cfg: "Config", *, create: bool = False) -> Path:
    """Return the noisy data directory and optionally create it."""
    return _directory(cfg.paths.noisy, create)


def results_dir(cfg: "Config", rq_name: str, *, create: bool = False) -> Path:
    """Return the results directory for the named workstream."""
    if not rq_name.isidentifier():
        raise ValueError("rq_name must be a directory name such as rq1")
    return _directory(str(Path(cfg.paths.results) / rq_name), create)
