"""Replay the final RQ1 experiment on a frozen, entity-disjoint subset."""

import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from experiments.rq1.run_rq1 import run_experiment
from src.common.config import load_config
from src.common.data.loader import load_noisy
from src.common.data.splitting import apply_split, load_split
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.linking.bloom import BloomLinker
from src.common.paths import app_dir
from src.common.preprocessing.field_builder import build_field_strings
from src.common.similarity.dice import dice_matrix

GOLDEN = Path(__file__).parent / "golden" / "rq1"
TOLERANCE = 1e-9


def golden_config():
    cfg = load_config("rq1")
    data = GOLDEN.resolve().relative_to(app_dir())
    return replace(
        cfg,
        paths=replace(
            cfg.paths,
            prepared=str(data / "prepared"),
            splits=str(data / "splits"),
            noisy=str(data / "noisy"),
        ),
    )


def bloom_artifacts(test, cfg, field_set, tau):
    settings = cfg.bloom
    encoder = BloomFilterEncoder(
        settings.l, settings.k, settings.q, bytes.fromhex(settings.hmac_key), settings.pad_char
    )
    features = test.drop(columns=cfg.columns.entity_id)
    strings = build_field_strings(features, field_set, cfg, normalize=True)
    bits = encoder.encode_many(strings)
    pairs = np.triu_indices(len(strings), k=1)
    scores = dice_matrix(bits, bits)[pairs]
    return {
        "record_ids": strings.index.tolist(),
        "filter_sha256": [hashlib.sha256(row.tobytes()).hexdigest() for row in bits],
        "dice": scores.tolist(),
        "edges": (scores >= tau).tolist(),
        "cluster_labels": BloomLinker("bloom_fuzzy", field_set, tau, cfg).link(features).tolist(),
    }


def assert_artifacts(actual, expected):
    for field in ("record_ids", "filter_sha256", "edges", "cluster_labels"):
        assert actual[field] == expected[field]
    assert actual["dice"] == pytest.approx(expected["dice"], rel=0, abs=TOLERANCE)


def test_rq1_golden(tmp_path):
    cfg = golden_config()
    manifest = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))
    seed = manifest["seed"]
    levels = cfg.noise_levels
    output = run_experiment(cfg, seeds=[seed], out_dir=tmp_path)
    runs = pd.read_csv(output / "raw_runs.csv").drop(columns="runtime_sec")
    pd.testing.assert_frame_equal(
        runs, pd.read_csv(GOLDEN / "raw_runs.csv"), rtol=0, atol=TOLERANCE
    )
    pd.testing.assert_frame_equal(
        pd.read_csv(output / "tau_selection.csv"),
        pd.read_csv(GOLDEN / "tau_selection.csv"),
        rtol=0,
        atol=TOLERANCE,
    )

    with gzip.open(GOLDEN / "bloom.json.gz", "rt", encoding="utf-8") as handle:
        bloom = json.load(handle)
    split = load_split(GOLDEN / "splits" / f"split_seed{seed}.json")
    for level in levels:
        frame = load_noisy(seed, level, cfg)
        assert len(frame) == manifest["n_records"] <= 200
        _, test = apply_split(frame, split, cfg)
        for row in runs.loc[
            (runs["noise_level"] == level) & (runs["method"] == "bloom_fuzzy")
        ].itertuples():
            assert_artifacts(bloom_artifacts(test, cfg, row.field_set, row.tau), bloom[row.run_id])
