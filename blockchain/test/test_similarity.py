import numpy as np
import pytest
from src.common.similarity.dice import dice_pair


def test_dice_similarity_for_identical_and_disjoint_filters():
    first = np.array([1, 0, 1, 0], dtype=np.uint8)
    assert dice_pair(first, first) == 1.0
    assert dice_pair(first, 1 - first) == 0.0
    assert dice_pair(first * 0, first * 0) == 0.0


def test_dice_rejects_different_lengths():
    with pytest.raises(ValueError, match="same width"):
        dice_pair(np.array([1]), np.array([1, 0]))
