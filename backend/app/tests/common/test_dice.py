import numpy as np
import pytest

from src.common.seeding import make_rng
from src.common.similarity.dice import compute_similar_pairs, dice_matrix, dice_pair


def test_dice_hand_calculations_and_symmetry():
    a = np.array([[1, 1, 0, 0], [0, 0, 0, 0]], dtype=np.uint8)
    b = np.array([[1, 0, 1, 1], [0, 0, 1, 0], [1, 1, 0, 0], [0, 0, 0, 0]], dtype=np.uint8)
    expected = np.array([[2 / 5, 0, 1, 0], [0, 0, 0, 0]])
    np.testing.assert_array_equal(dice_matrix(a, b), expected)
    np.testing.assert_array_equal(dice_matrix(b, a), expected.T)
    assert dice_pair(a[0], b[0]) == 2 / 5
    assert dice_pair(a[0], b[2]) == 1.0
    assert dice_pair(a[0], b[1]) == 0.0
    assert dice_pair(a[1], b[3]) == 0.0


@pytest.mark.parametrize("block_size", [1, 4, 1000])
@pytest.mark.parametrize("tau", [0.0, 0.5, 1.0])
def test_blockwise_matches_dense_upper_triangle(block_size, tau):
    rng = make_rng(0, "test_dice_blocks")
    bits = rng.integers(0, 2, size=(15, 23), dtype=np.uint8)
    bits[0] = 0
    bits[2] = bits[1]
    dense = dice_matrix(bits, bits)
    expected_i, expected_j = np.nonzero(np.triu(dense >= tau, k=1))
    i, j, scores = compute_similar_pairs(bits, tau, block_size)
    order = np.lexsort((j, i))
    assert (i < j).all() and (scores >= tau).all()
    np.testing.assert_array_equal(i[order], expected_i)
    np.testing.assert_array_equal(j[order], expected_j)
    np.testing.assert_array_equal(scores[order], dense[expected_i, expected_j])


def test_empty_and_single_row_have_no_pairs():
    for n in (0, 1):
        arrays = compute_similar_pairs(np.zeros((n, 12), dtype=np.uint8), 0.0)
        assert all(array.shape == (0,) for array in arrays)
        assert np.issubdtype(arrays[0].dtype, np.integer)
