import numpy as np
import pandas as pd

from src.common.config import load_config
from src.common.linking.diagnostic_variants import DosageBlockedBloomLinker, PreparedStar


def test_hybrid_blocks_even_identical_descriptions_at_different_dosage():
    cfg = load_config("rq1")
    records = pd.DataFrame({
        "record_id": ["1", "2", "3", "4"],
        "raw_item_description": ["Product"] * 4,
        "dosage": ["20 MG", "20mg", "10mg", None],
    })
    linker = DosageBlockedBloomLinker(cfg)
    assert linker.prepare(records, 1).labels_at(1).tolist() == [0, 0, 1, 2]


def test_star_refuses_to_chain_through_a_non_leader():
    scores = np.array([[1.0, 0.9, 0.4], [0.9, 1.0, 0.9], [0.4, 0.9, 1.0]])
    prepared = PreparedStar(pd.Index(["a", "b", "c"]), scores, 0)
    assert prepared.labels_at(0.8).tolist() == [0, 0, 1]
    assert prepared.labels_at(0).tolist() == [0, 0, 0]
    assert prepared.labels_at(1).tolist() == [0, 1, 2]
