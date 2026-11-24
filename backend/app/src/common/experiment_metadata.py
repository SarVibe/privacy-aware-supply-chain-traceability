import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path
from collections.abc import Sequence

import pandas as pd

from src.common.config import Config, load_config, positive_integer
from src.common.experiment.io import write_csv
from src.common.linking.threshold import threshold_values


def add_common_args(ap: argparse.ArgumentParser) -> argparse.ArgumentParser:
    cfg = load_config("rq2")
    ap.add_argument("--data", default=None,
                    help="CSV dataset (default: the configured real shipment dataset)")
    ap.add_argument("--column", default="raw_item_description")
    ap.add_argument("--composite", action="store_true")
    ap.add_argument("--composite-columns", nargs="+", default=None)
    ap.add_argument("--n-entities", type=int, default=None)
    ap.add_argument("--n-records", type=int, default=cfg.sweep.victim_draws)
    ap.add_argument("--seeds", type=int, default=len(cfg.seeds))
    ap.add_argument("--n-selection", type=int, default=cfg.sweep.selection_seeds,
                    help="number of initial seeds reserved for operating-point selection")
    ap.add_argument("--q", type=int, default=cfg.bloom.q)
    ap.add_argument("--pad", action="store_true", default=True)
    ap.add_argument("--standard", default=f"{cfg.bloom.l}:{cfg.bloom.k}",
                    help="standard Bloom configuration as l:k")
    return ap


def parse_standard(value: str) -> tuple[int, int]:
    try:
        l, k = (int(part.strip()) for part in value.split(":"))
    except (AttributeError, ValueError):
        raise ValueError("--standard must be in l:k format") from None
    return positive_integer(l, "l"), positive_integer(k, "k")


def data_fingerprint(path: str | None) -> dict:
    if path:
        p = Path(path)
        if p.exists():
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            return {"path": str(p.resolve()), "sha256": digest}
    return {"path": None, "sha256": None}


def package_versions() -> dict:
    names = ("numpy", "pandas", "scipy", "matplotlib", "pytest", "tabulate")
    versions = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    versions["python"] = sys.version.split()[0]
    return versions


def config_metadata(q: int | None = None, pad: bool | None = None,
                    data_mode: str | None = None, *, cfg: Config | None = None,
                    tau_grid: Sequence[float] | None = None) -> dict:
    cfg = cfg or load_config("rq2")
    sweep = cfg.sweep
    bloom = cfg.bloom
    return {
        "q": bloom.q if q is None else q,
        "pad": True if pad is None else pad,
        "pad_char": bloom.pad_char,
        "hmac_key_fingerprint": hashlib.sha256(bytes.fromhex(bloom.hmac_key)).hexdigest()[:12],
        "data_mode": "composite" if data_mode == "composite" else "description",
        "tau_grid": list(threshold_values(cfg.tau_grid) if tau_grid is None else tau_grid),
        "degenerate_fill": sweep.degenerate_fill,
        "standard": [bloom.l, bloom.k],
        "reid_topk": list(sweep.reid_topk),
        "reid_delta": sweep.reid_delta,
        "bit_top": sweep.bit_top,
        "n_records": sweep.victim_draws,
        "seeds": list(cfg.seeds),
        "extra_columns": list(cfg.columns.text[1:]),
        "noise_fields": list(cfg.noise_fields),
        "typos_per_selected_record": list(cfg.typos_per_selected_record),
    }


def write_run_csv(df: pd.DataFrame, csv_path: str | Path, *,
                  cfg: Config | None = None, tau_grid: Sequence[float] | None = None,
                  q: int | None = None, pad: bool | None = None,
                  data_mode: str | None = None, dataset_path: str | None = None,
                  argv: list[str] | None = None, nominal_noise: float | None = None,
                  unchanged_fraction: float | None = None,
                  average_normalized_edit_distance: float | None = None,
                  nominal_noise_rates: list[float] | None = None,
                  source_runs: dict | None = None,
                  analysis_scope: dict | None = None) -> None:
    csv_path = Path(csv_path)
    write_csv(df, csv_path)
    meta = {
        "experiment_config": config_metadata(q=q, pad=pad, data_mode=data_mode, cfg=cfg, tau_grid=tau_grid),
        "package_versions": package_versions(),
        "argv": sys.argv if argv is None else argv,
        "dataset_fingerprint": data_fingerprint(dataset_path),
        "source_runs": source_runs or {},
        "analysis_scope": analysis_scope or {},
        "noise": {
            "nominal_noise_rate": nominal_noise,
            "nominal_noise_rates": nominal_noise_rates,
            "unchanged_fraction_after_normalization": unchanged_fraction,
            "average_normalized_edit_distance": average_normalized_edit_distance,
        },
    }
    text = json.dumps(meta, indent=2)
    csv_path.with_name("run_meta.json").write_text(text, encoding="utf-8")
    csv_path.with_name(csv_path.stem + "_run_meta.json").write_text(text, encoding="utf-8")


def write_markdown(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    try:
        text = df.to_markdown(index=False)
    except ImportError:
        headers = [str(column) for column in df.columns]
        text = "| " + " | ".join(headers) + " |\n"
        text += "| " + " | ".join("---" for _ in headers) + " |\n"
        for row in df.itertuples(index=False, name=None):
            text += "| " + " | ".join("" if value is None else str(value) for value in row) + " |\n"
    path.write_text(text, encoding="utf-8")


def write_metadata(
    path: str | Path,
    cfg: object,
    seeds: list[int] | tuple[int, ...],
    extra: dict | None = None,
) -> None:
    """Write experiment provenance with a fingerprint in place of the HMAC key."""
    import platform
    import subprocess
    from dataclasses import asdict
    from datetime import datetime, timezone

    snapshot = asdict(cfg)
    if snapshot.get("sweep") is None:
        snapshot.pop("sweep", None)
    key = snapshot["bloom"].pop("hmac_key")
    snapshot["bloom"]["hmac_key_fingerprint"] = hashlib.sha256(bytes.fromhex(key)).hexdigest()[:12]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        commit = None
    metadata = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "package_versions": package_versions(),
        "platform": platform.platform(),
        "git_commit": commit,
        "config": snapshot,
        "seeds": list(seeds),
        "extra": {} if extra is None else extra,
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
