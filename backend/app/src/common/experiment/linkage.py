"""Evaluate record-level linkage on shared validation and test data."""

from collections.abc import Sequence
from dataclasses import replace

from src.common.data.loader import LinkageData
from src.common.encoding.bloom_filter import PostTransform
from src.common.evaluation.metrics import evaluate_clusters
from src.common.linking.base import Linker
from src.common.linking.bloom import BloomLinker
from src.common.linking.threshold import select_single_tau, tune_tau


def evaluate_test_clusters(data: LinkageData, linker: Linker) -> dict[str, float | int]:
    """Score connected-component labels without exposing the truth to the linker."""
    eid, rid = data.config.columns.entity_id, data.config.columns.record_id
    truth = data.test.set_index(rid)[eid]
    return evaluate_clusters(truth, linker.link(data.test.drop(columns=eid)))


def evaluate_bloom_linkage(
    data: LinkageData, noise: float, l: int, k: int, q: int, taus: Sequence[float],
    *, tau: float | None = None, post_transform: PostTransform | None = None,
) -> dict[str, float | int]:
    """Tune on validation records (unless tau is supplied), then score the test split."""
    cfg = replace(data.config, bloom=replace(data.config.bloom, l=l, k=k, q=q))
    if tau is None:
        table = tune_tau(
            {noise: data.validation}, taus,
            {"cfg": cfg, "field_set": data.field_set, "post_transform": post_transform},
        )
        tau = select_single_tau(table)
    linker = BloomLinker("bloom", data.field_set, tau, cfg, post_transform=post_transform)
    return {"tau": tau, **evaluate_test_clusters(data, linker)}
