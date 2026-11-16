import pytest
from bitarray import bitarray

from src.similarity import DiceSimilarityEngine


def test_dice_similarity_for_identical_and_disjoint_filters():
    first = bitarray("11001100")
    identical = bitarray("11001100")
    disjoint = bitarray("00110011")

    assert DiceSimilarityEngine.calculate_dice(first, identical) == 1.0
    assert DiceSimilarityEngine.calculate_dice(first, disjoint) == 0.0


def test_dice_rejects_different_lengths():
    with pytest.raises(ValueError, match="length mismatch"):
        DiceSimilarityEngine.calculate_dice(bitarray("1"), bitarray("10"))