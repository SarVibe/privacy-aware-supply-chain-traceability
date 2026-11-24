"""Load paired noise variants and prepare the per-seed cohorts."""

import hashlib
import hmac
import os
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from src.common.config import Config
from src.common.data.loader import align_noisy_records, load_noisy
from src.common.data.splitting import apply_reference_partition, partition_reference_entities
from src.common.encoding.bloom_filter import BloomFilterEncoder
from src.common.seeding import make_rng
from src.rq2.collision_config import CollisionConfig
from src.rq2.collision_linkage import build_collision_encoder, cohort_tokens


@dataclass(frozen=True)
class Cohort:
    frame: pd.DataFrame
    tokens: list[set[str]]
    parties: NDArray[np.int8]


def load_experiment_root(cfg: CollisionConfig, rq1: Config) -> bytes:
    raw = os.environ.get(cfg.key_env, "")
    try:
        root = bytes.fromhex(raw)
    except ValueError:
        root = b""
    if len(root) < hashlib.sha256().digest_size or root == bytes.fromhex(rq1.bloom.hmac_key):
        raise ValueError(f"{cfg.key_env} must contain at least 32 private bytes encoded as hexadecimal")
    return root


def derive_experiment_keys(root: bytes, seed: int) -> tuple[bytes, bytes]:
    return (hmac.digest(root, f"rq2:bloom:{seed}".encode(), "sha256"),
            hmac.digest(root, f"rq2:exact:{seed}".encode(), "sha256"))


def build_seed_partition(
    base: pd.DataFrame, rq1: Config, cfg: CollisionConfig, seed: int, *, pilot: bool = False
) -> dict[str, list[str]]:
    entities = sorted(base[rq1.columns.entity_id].unique())
    validation, test, reference = cfg.split_fractions
    split = partition_reference_entities(entities, validation, test, make_rng(seed, "rq2:entity-splits"))
    if pilot:
        rng = make_rng(seed, "rq2:pilot-sample")
        total = cfg.pilot.max_entities
        target = min(total - 1, max(1, round(total * validation / (validation + reference))))
        for name, cap in (("validation", target), ("reference", total - target)):
            split[name] = sorted(rng.choice(split[name], size=min(len(split[name]), cap), replace=False).tolist())
    return split


def load_collision_cohorts(
    base: pd.DataFrame, rq1: Config, cfg: CollisionConfig, seed: int, noise: float,
    split: dict[str, list[str]], encoder: BloomFilterEncoder, *, include_test: bool = True,
) -> dict[str, Cohort]:
    frame = base if noise == 0 else align_noisy_records(base, load_noisy(seed, noise, rq1), rq1)
    entities = set().union(*map(set, split.values()))
    frame = frame.loc[frame[rq1.columns.entity_id].isin(entities)]
    cohorts = {}
    for name, partition in apply_reference_partition(frame, split, rq1).items():
        if name == "test" and not include_test:
            continue
        # Synthetic organizations divide the same observations, preserving unordered pair eligibility.
        parties = np.zeros(len(partition), dtype=np.int8)
        order = make_rng(seed, f"rq2:pseudo-party:{name}").permutation(len(partition))
        parties[order[len(partition) // 2:]] = 1
        cohorts[name] = Cohort(partition, cohort_tokens(partition, rq1, cfg.field_set, encoder), parties)
    return cohorts


def encoder_for_cell(rq1: Config, pair: tuple[int, int], key: bytes) -> BloomFilterEncoder:
    length, hashes = pair
    return build_collision_encoder(replace(rq1, bloom=replace(rq1.bloom, l=length, k=hashes, hmac_key=key.hex())))
