import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]


def test_frozen_rq2_v1_and_rq1_artifacts():
    manifest = json.loads((ROOT / "docs/v1_hashes.json").read_text(encoding="utf-8"))["sha256"]
    v1 = ROOT / "backend/app/results/rq2"
    rq1 = ROOT / "backend/app/results/rq1"
    if not v1.exists() and not rq1.exists():
        pytest.skip("Restore the archived RQ1 and RQ2 v1 results to verify their hashes")
    expected = {name for name in manifest if name.startswith("backend/app/results/rq2/")}
    actual = {path.relative_to(ROOT).as_posix() for path in v1.rglob("*") if path.is_file()}
    problems = [f"Unexpected file: {name}" for name in sorted(actual - expected)]
    for name, digest in manifest.items():
        path = ROOT / name
        if not path.is_file():
            problems.append(f"Missing file: {name}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"Changed file: {name}")
    assert not problems, "\n".join(problems)
