import math

import numpy as np

from src.common.encoding.randomized_response import flip_probability, response_transform


def test_response_transform_is_seeded_and_infinite_epsilon_is_identity():
    bits = np.zeros(1024, dtype=np.uint8)
    assert flip_probability(math.inf, 4) == 0
    assert response_transform(0, 1024, 4, math.inf) is None
    first = response_transform(0, 1024, 4, 2)
    replay = response_transform(0, 1024, 4, 2)
    other = response_transform(1, 1024, 4, 2)
    once, twice = first(bits), first(bits)
    np.testing.assert_array_equal(once, replay(bits))
    np.testing.assert_array_equal(twice, replay(bits))
    assert np.any(once != other(bits)) and bits.sum() == 0
